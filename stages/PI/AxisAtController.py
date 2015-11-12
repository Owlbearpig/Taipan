# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 14:23:33 2015

@author: Arno Rehn
"""

from common import Manipulator
from asyncioext import ensure_weakly_binding_future
import asyncio
import re
import enum

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

    def __init__(self, connection = None, address = 1, axis = 1):
        super().__init__()
        self.connection = connection
        self.address = address
        self.axis = axis
        self._identification = None
        self._status = 0x0
        self._isReferenced = False
        self._isMovingFuture = asyncio.Future()
        self._movementStopped = True

        ensure_weakly_binding_future(self.updateStatus)

    def __del__(self):
        print("deleted AxisAtController!")

    def handleError(self, msg):
        errorCode = int(msg)
        if errorCode == 0: # no error
            pass
        elif errorCode == 10: # stopped movement, this is okay.
            pass
        else:
            raise Exception("Unhandled error code %d on PI Controller %s "
                            "(axis %d)" %
                            (errorCode, self._identification, self.axis))
    async def updateStatus(self):
        while True:
            await asyncio.sleep(0.5)

            if (self.connection is None):
                continue

            await self.singleUpdate()

    async def singleUpdate(self):
        self._status = await self.send("SRG?", 1)

        self._position = await self.send(b'POS?')
        self._isReferenced = bool(await self.send(b'FRF?'))
        if not self._isMovingFuture.done() and not self.isMoving:
            self._isMovingFuture.set_result(self._movementStopped)

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

        isRequest = command[-1] == ord(b'?')

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
            expected = ' '.join([ str(x) for x in args])
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

    async def initialize(self):
        self._identification = await self.send(b'*IDN?', includeAxis=False)
        self._hardwareMinimum = await self.send(b'TMN?')
        self._hardwareMaximum = await self.send(b'TMX?')
        self._position = await self.send(b'POS?')
        self.velocity = await self.send(b'VEL?')
        self._isReferenced = bool(await self.send(b'FRF?'))

        await self.send("RON", 1);
        await self.send("SVO", 1);

    @property
    def isMoving(self):
        return bool(self._status & self.StatusBits.Moving.value) or \
               self.isReferencing

    @property
    def isServoOn(self):
        return bool(self._status & self.StatusBits.ServoMode.value)

    @property
    def isReferencing(self):
        return bool(self._status & self.StatusBits.Referencing.value)

    @property
    def isOnTarget(self):
        return bool(self._status & self.StatusBits.OnTarget.value)

    @property
    def isReferenced(self):
        return self._isReferenced

    @property
    def status(self):
        if (self.isOnTarget):
            return self.Status.TargetReached
        elif (self.isMoving):
            return self.Status.Moving

    @property
    def value(self):
        return self._position

    async def moveTo(self, val, velocity = None):
        if velocity is None:
            velocity = self.velocity

        await self.send("VEL", velocity)

        self._movementStopped = False
        await self.send("MOV", val)
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture
        return self.isOnTarget and not self._movementStopped

    # 0.75 mm buffer for acceleration and proper trigger position
    async def beginScan(self, start, stop, velocity = None):
        if stop > start:
            await self.moveTo(start - 0.75, velocity)
        else:
            await self.moveTo(start + 0.75, velocity)

    def stop(self):
        self._movementStopped = True
        asyncio.ensure_future(self.send("HLT"))

    async def reference(self):
        self._movementStopped = False
        await self.send("FRF")
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture
        return self.isReferenced

    async def configureTrigger(self, step, start = None, stop = None,
                               triggerId = 1):
        if start is None or stop is None:
            raise Exception("The start and stop parameters are mandatory!")

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
        self._trigStep = await self.send(b"CTO?", triggerId, 1,
                                         includeAxis=False)
        self._trigStart = await self.send(b"CTO?", triggerId, 10,
                                          includeAxis=False)
        self._trigStop = await self.send(b"CTO?", triggerId, 9,
                                         includeAxis=False)

        return self._trigStep, self._trigStart, self._trigStop
