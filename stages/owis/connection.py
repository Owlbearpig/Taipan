# -*- coding: utf-8 -*-
"""
Created on Fri Jul 15 12:51:40 2016

@author: Arno Rehn
"""

from common import ComponentBase
from serial import Serial
from threading import Lock
from asyncioext import threaded_async


class Connection(ComponentBase):
    def __init__(self, port=None, baudRate=9600):
        super().__init__()
        self.port = port
        self.baudRate = baudRate
        self.serial = Serial()
        self._lock = Lock()

    async def __aenter__(self):
        await super().__aenter__()
        self.open()
        await self.send('comend=2\r')
        msg = await self.send('?msg')

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self.close()

    def open(self):
        """ Opens the Connection, potentially closing an old Connection
        """
        self.close()
        self.serial.port = self.port
        self.serial.open()

    def close(self):
        """ Closes the Connection.
        """
        if self.serial.isOpen():
            self.serial.close()

    @threaded_async
    def send(self, command):
        """ Send a command over the Connection. If the command is a request,
        returns the reply.

        Parameters
        ----------
        command (convertible to bytearray) : The command to be sent.
        """

        with self._lock:
            # convert `command` to a bytearray
            if isinstance(command, str):
                command = bytearray(command, 'ascii')
            else:
                command = bytearray(command)

            isRequest = command[0] == ord(b'?')

            command += b'\n'

            self.serial.write(command)

            # no request -> no reply. just return.
            if not isRequest:
                return

            # return reply
            return self.serial.readline().strip().decode('ascii')


if __name__ == '__main__':
    import asyncio

    loop = asyncio.get_event_loop()

    async def run():
        async with Connection('/tmp/owis') as conn:
            await conn.send('init3')
            print("Position:", await conn.send('?cnt3'))
            await conn.send('stop3')
            message = await conn.send('?astat')
            print(message)

    loop.run_until_complete(run())
