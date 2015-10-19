# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 14:23:33 2015

@author: Arno Rehn
"""

from common import Manipulator
import re

_replyExpression = re.compile(b'([0-9]+) ([0-9]+) (.*)')
_axisValueExpression = re.compile(b'([0-9\\.]+)=([0-9\\.]+)')

class AxisAtController(Manipulator):
    def __init__(self, connection = None, address = 1, axis = 1):
        super().__init__()
        self.connection = connection
        self.address = address
        self.axis = axis

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

    async def send(self, command, value = None):
        # convert `command` to a bytearray
        if isinstance(command, str):
            command = bytearray(command, 'ascii')

        command = b'%d %s' % (self.address, command)
        if value is not None:
            command = b'%s %d %a' % (command, self.axis, value)

        ret = await self.connection.send(command)

        if command[-1] != ord(b'?'):
            self.handleError(await self.send(b'ERR?'))
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
        self._identification = await self.send(b'*IDN?')
        self._hardwareMinimum = await self.send(b'TMN?')
        self._hardwareMaximum = await self.send(b'TMX?')
        self._position = await self.send(b'POS?')
        self._velocity = await self.send(b'VEL?')
