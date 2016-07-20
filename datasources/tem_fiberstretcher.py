# -*- coding: utf-8 -*-
"""
Created on Wed Jul 20 16:07:15 2016

@author: Arno Rehn
"""

from common import DataSource, ureg, Q_
from asyncioext import threaded_async
from threading import Lock
import re


_replyExpression = re.compile(br'([a-zA-Z0-9]+)=\s*([0-9]+)')


class TEMFiberStretcher(DataSource):

    def __init__(self, controlPort, dataPort, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self.controlPort = controlPort
        self.dataPort = dataPort

        self.commLock = Lock()

    @classmethod
    def _sanitizeCommand(cls, cmd):
        # convert `cmd` to a bytearray
        if isinstance(cmd, str):
            cmd = bytearray(cmd, 'ascii')
        else:
            cmd = bytearray(cmd)

        cmd = cmd.lower()
        return cmd

    def query(self, var):
        reply = self.send(var + b'=\r\n')
        return reply

    def setVar(self, var, value):
        value = int(value)

    def send(self, command, nReplies=1):
        command = self._sanitizeCommand(command)
        with self.commLock:
            self.controlPort.write(command + b'\r\n')

            replies = []

            while nReplies:
                replies.append(self.controlPort.readline().strip())
                nReplies -= 1

            return replies

    async def __aenter__(self):
        await super().__aenter__(self)
#        self.query()
        return self

if __name__ == '__main__':
    from serial import Serial

#    fs = TEMFiberStretcher(Serial('/tmp/fiberstretcher0', 57600), None)
#    print(fs.send('helloaa'))
#    print(fs.query('RecInterval'))

    reply = b'RecInterval= 20'
    match = _replyExpression.match(reply)
    print(match.groups())
