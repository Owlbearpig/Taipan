# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2015 - 2016 Arno Rehn <arno@arnorehn.de>

Taipan is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Taipan is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Taipan.  If not, see <http://www.gnu.org/licenses/>.
"""
import logging

from common import Manipulator, action
from asyncioext import ensure_weakly_binding_future
import asyncio
import re
import enum
import traitlets
from common import ureg, Q_
import numpy as np

_replyExpression = re.compile(br'([0-9]+) ([0-9]+) (.*)')
_valueExpression = re.compile(br'([0-9 ]+)=([0-9a-fA-Fx\.\-]+)$')


class AxisAtController(Manipulator):
    class StatusBits(enum.Enum):
        NegativeLimitSwitch = 0x1
        ReferenceSwitch = 0x2
        PositiveLimitSwitch = 0x4
        # 0x8 not used
        DigInput_1 = 0x10
        DigInput_2 = 0x20
        DigInput_3 = 0x40
        DigInput_4 = 0x80
        ErrorFlag = 0x100
        # 0x200 not used
        # 0x400 not used
        # 0x800 not used
        ServoMode = 0x1000
        Moving = 0x2000
        Referencing = 0x4000
        OnTarget = 0x8000

    def __init__(self, connection=None, address=1, axis=1):
        super().__init__()
        self.connection = connection
        self.address = address
        self.axis = axis
        self._identification = None
        self._status = 0x0
        self._isReferenced = False
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)

    async def __aenter__(self):
        await super().__aenter__()

        self._identification = await self.send(b'*IDN?', includeAxis=False)
        self._hardwareMinimum = await self.send(b'TMN?')
        self._hardwareMaximum = await self.send(b'TMX?')
        self.velocity = Q_(await self.send(b'VEL?'), 'mm/s')
        self._isReferenced = bool(await self.send(b'FRF?'))

        await self.send("RON", 1)
        await self.send("SVO", 1)

        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()

    def handleError(self, msg):
        errorCode = int(msg)
        if errorCode == 0:  # no error
            pass
        elif errorCode == 10:  # stopped movement, this is okay.
            pass
        else:
            raise Exception("Unhandled error code %d on PI Controller %s "
                            "(axis %d)" %
                            (errorCode, self._identification, self.axis))

    isMoving = traitlets.Bool(False, read_only=True)
    isServoOn = traitlets.Bool(False, read_only=True)
    isReferencing = traitlets.Bool(False, read_only=True)
    isOnTarget = traitlets.Bool(False, read_only=True)
    isReferenced = traitlets.Bool(False, read_only=True)

    async def updateStatus(self):
        while True:
            await asyncio.sleep(0.5)
            if (self.connection is None):
                continue

            await self.singleUpdate()

    async def singleUpdate(self):
        movFut = self._isMovingFuture

        self._status = await self.send("SRG?", 1)

        self.set_trait('value', Q_(await self.send(b'POS?'), 'mm'))

        self.set_trait('isReferenced', bool(await self.send(b'FRF?')))
        self.set_trait('isReferencing',
                       bool(self._status & self.StatusBits.Referencing.value))
        self.set_trait('isOnTarget',
                       bool(self._status & self.StatusBits.OnTarget.value))
        self.set_trait('isServoOn',
                       bool(self._status & self.StatusBits.ServoMode.value))
        self.set_trait('isMoving',
                       bool(self._status & self.StatusBits.Moving.value) or
                       self.isReferencing)

        if self.isMoving:
            self.set_trait('status', self.Status.Moving)
        else:
            self.set_trait('status', self.Status.Idle)

        if not movFut.done() and not self.isMoving:
            movFut.set_result(None)


    async def send(self, command, *args, includeAxis=True):
        """ Send a command to the controller. The axis ID will automatically
        appended, unless specified otherwise. If the command is a request,
        the reply will be parsed (if possible) and returned. Otherwise,
        an error request is automatically sent and its reply passed to the
        ``handleError`` method.

        Parameters
        ----------
        command (convertible to bytearray) : The command to be sent.

        *args : The arguments transmitted with the command.

        includeAxis (bool, optional) : Whether to transmit the axis id as the
        first argument to the command. Defaults to ``True``
        """
        if self.connection is None:
            return None

        # convert `command` to a bytearray
        if isinstance(command, str):
            command = bytearray(command, 'ascii')

        isRequest = (command[-1] == ord(b'?'))

        command = b'%d %s' % (self.address, command)

        if includeAxis:
            args = (self.axis,) + args

        ret = await self.connection.send(command, *args)

        if not isRequest:
            self.handleError(await self.send(b'ERR?', includeAxis=False))
            return

        match = _replyExpression.match(ret)
        if not match:
            raise Exception("Unexpected reply %s to command %s" %
                            (ret, command))

        (dest, src, msg) = match.groups()
        dest = int(dest)
        src = int(src)
        if src != self.address:
            raise Exception("Got reply %s for controller %d, but own address "
                            "is %d (sent: %s)" %
                            (msg, dest, self.address, command))

        match = _valueExpression.match(msg)
        if match:
            (params, value) = match.groups()
            params = params.decode('ascii')
            expected = ' '.join([str(x) for x in args])
            if params != expected:
                raise Exception("Got reply params %s, but expected %s "
                                "(sent: %s)" % (params, expected, command))
            try:
                if b'.' in value:
                    return float(value)
                elif value.startswith(b'0x'):
                    return int(value, 16)
                else:
                    return int(value)
            except ValueError:
                return value
        else:
            return msg

    async def moveTo(self, val: float, velocity=None):
        if velocity is None:
            velocity = self.velocity

        await self.send("VEL", velocity.to('mm/s').magnitude)

        await self.send("MOV", val.to('mm').magnitude)
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

        return self.isOnTarget

    def stop(self):
        asyncio.ensure_future(self.send("HLT"))

        if not self._isMovingFuture.done():
            self._isMovingFuture.cancel()

    @action("Home to ref. switch")
    async def reference(self):
        await self.send("FRF")
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture
        return self.isReferenced

    async def configureTrigger(self, axis, triggerId=1):
        axis = axis.to('mm').magnitude

        step = np.mean(np.diff(axis))
        start = axis[0]

        N = len(axis)
        # let the trigger output end half a step after the last position
        stop = start + (N - 1) * step + step / 2

        # enable trig output on axis
        await self.send(b"CTO", triggerId, 2, self.axis, includeAxis=False)

        # set trig output to pos+offset mode
        await self.send(b"CTO", triggerId, 3, 7, includeAxis=False)

        # set trig distance to ``step``
        await self.send(b"CTO", triggerId, 1, step, includeAxis=False)

        # trigger start position
        await self.send(b"CTO", triggerId, 10, start, includeAxis=False)

        # trigger stop position
        await self.send(b"CTO", triggerId, 9, stop, includeAxis=False)

        # enable trigger output
        await self.send(b"TRO", triggerId, 1, includeAxis=False)

        # ask for the actually set start, stop and step parameters
        self._trigStep = Q_(await self.send(b"CTO?", triggerId, 1,
                                            includeAxis=False), 'mm')
        self._trigStart = Q_(await self.send(b"CTO?", triggerId, 10,
                                             includeAxis=False), 'mm')
        self._trigStop = Q_(await self.send(b"CTO?", triggerId, 9,
                                            includeAxis=False), 'mm')

        return np.arange(self._trigStart.magnitude, self._trigStop.magnitude,
                         self._trigStep.magnitude) * ureg.mm
