# -*- coding: utf-8 -*-
"""
Created on Wed Jul 20 16:07:15 2016

@author: Arno Rehn
"""

import asyncio
from common import DataSource, ureg, Q_
from asyncioext import threaded_async
from threading import Lock
import re
from serial import Serial, aio as aioserial
from serial.threaded import LineReader


_replyExpression = re.compile(r'([a-zA-Z0-9]+)=\s*([0-9]+)')


class TEMFiberStretcher(DataSource):

    _lineReader = None

    def __init__(self, controlPort, dataPort, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self.controlPort = controlPort
        self.dataPort = dataPort
        self.commLock = Lock()

    @classmethod
    def _sanitizeCommand(cls, cmd):
        cmd = cmd.lower()
        return cmd

    def query(self, var):
        reply = self.send(var + '=')

    def setVar(self, var, value):
        value = int(value)

    def send(self, command):
        command = self._sanitizeCommand(command)
        self._lineReader.write_line(command)

    def handle_line(self, line):
        print(line)

    async def __aenter__(self):
        await super().__aenter__()

        self._controlTransport, self._lineReader = \
            await aioserial.create_serial_connection(self._loop, LineReader,
                                                     self.controlPort,
                                                     baudrate=57600)
        self._lineReader.handle_line = self.handle_line
        await asyncio.sleep(0)

        return self

if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    async def run():
        async with TEMFiberStretcher('/tmp/fiberstretcher0', None, loop=loop) as fs:
            fs.send('hello')
            await asyncio.sleep(2)

    loop.run_until_complete(run())


#    print(fs.send('hello'))
#    print(fs.query('RecInterval'))

#    reply = 'RecInterval asd= 20'
#    match = _replyExpression.match(reply)
#    assert match, 'failed'
#