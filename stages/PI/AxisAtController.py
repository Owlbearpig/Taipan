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

_replyExpression = re.compile(b'([0-9]+) ([0-9]+) (.*)')
_axisValueExpression = re.compile(b'([0-9\\.]+)=([0-9\\.]+)')
_axisStatusRegExpression = re.compile(b'([0-9\\.]+) ([0-9\\.]+)=([0-9\\.x]+)')

class AxisAtController(Manipulator):
    class StatusBits(enum.Enum):
        NegativeLimitSwitch = 0x1,
        ReferenceSwitch = 0x2,
        PositiveLimitSwitch = 0x4,
        # 0x8 not used
        DigInput_1 = 0x10,
        DigInput_2 = 0x20,
        DigInput_3 = 0x40,
        DigInput_4 = 0x80,
        ErrorFlag = 0x100,
        # 0x200 not used
        # 0x400 not used
        # 0x800 not used
        ServoMode = 0x1000,
        Moving = 0x2000,
        Referencing = 0x4000,
        OnTarget = 0x8000

    def __init__(self, connection = None, address = 1, axis = 1):
        super().__init__()
        self.connection = connection
        self.address = address
        self.axis = axis
        self._identification = None
        self._status = 0x0
        self._isReferenced = False
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

            ret = await self.send("SRG?", 1)
            match = _axisStatusRegExpression.match(ret)
            if not match:
                raise Exception("Unexpected reply %s to status request!" %
                                repr(ret))

            (axis, reg, val) = match.groups()
            axis = int(axis)
            reg = int(reg)
            val = int(val, 16)
            self._status = val

            self._position = await self.send(b'POS?')
            self._velocity = await self.send(b'VEL?')
            self._isReferenced = bool(await self.send(b'FRF?'))

    async def send(self, command, *args, includeAxis=True):
        if self.connection is None:
            return None

        # convert `command` to a bytearray
        if isinstance(command, str):
            command = bytearray(command, 'ascii')

        isRequest = command[-1] == ord(b'?')

        command = b'%d %s' % (self.address, command)

        ret = None
        if includeAxis:
            ret = await self.connection.send(command, self.axis, *args)
        else:
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

        match = _axisValueExpression.match(msg)
        if match:
            (axis, value) = match.groups()
            axis = int(axis)
            if axis != self.axis:
                raise Exception("Got value %s for axis %d, but expected axis "
                                "is %d (sent: %s)" %
                                (value, axis, self.axis, command))
            try:
                return int(value)
            except ValueError:
                return float(value)
        else:
            return msg

    async def initialize(self):
        self._identification = await self.send(b'*IDN?', includeAxis=False)
        self._hardwareMinimum = await self.send(b'TMN?')
        self._hardwareMaximum = await self.send(b'TMX?')
        self._position = await self.send(b'POS?')
        self._velocity = await self.send(b'VEL?')
        self._isReferenced = bool(await self.send(b'FRF?'))

    @property
    def isMoving(self):
        return bool(self._status & self.StatusBits.Moving) or \
               self.isReferencing

    @property
    def isServoOn(self):
        return bool(self._status & self.StatusBits.ServoMode)

    @property
    def isReferencing(self):
        return bool(self._status & self.StatusBits.Referencing)

    @property
    def isOnTarget(self):
        return bool(self._status & self.StatusBits.OnTarget)

    @property
    def isReferenced(self):
        return self._isReferenced
