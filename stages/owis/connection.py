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
