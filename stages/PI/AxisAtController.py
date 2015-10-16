# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 14:23:33 2015

@author: Arno Rehn
"""

from common import Manipulator
import re

_replyExpression = re.compile(b'([0-9]+) ([0-9]+) (.*)')

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
                            errorCode, self._identification, self.axis)

    async def send(self, command):
        # convert `command` to a bytearray
        if isinstance(command, str):
            command = bytearray(command, 'ascii')

        command = b'%d %s' % (self.address, command)
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

        return msg

    async def initialize(self):
        self._identification = await self.send('*IDN?')
