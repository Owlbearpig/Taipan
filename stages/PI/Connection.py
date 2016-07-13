# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 09:14:38 2015

@author: Arno Rehn
"""

from common import ComponentBase
from asyncioext import threaded_async
from serial import Serial
from threading import Lock

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
    def send(self, command, *args):
        """ Send a command over the Connection. If the command is a request,
        returns the reply.

        Parameters
        ----------
        command (convertible to bytearray) : The command to be sent.

        *args : Arguments to the command.
        """

        with self._lock:
            # convert `command` to a bytearray
            if isinstance(command, str):
                command = bytearray(command, 'ascii')
            else:
                command = bytearray(command)

            isRequest = command[-1] == ord(b'?')

            for arg in args:
                command += b' %a' % arg

            command += b'\n'

            self.serial.write(command)

            # no request -> no reply. just return.
            if not isRequest:
                return

            # read reply. lines ending with ' \n' are part of a multiline
            # reply.
            replyLines = []
            while len(replyLines) == 0 or replyLines[-1][-2:] == ' \n':
                replyLines.append(self.serial.readline())

            return b''.join(replyLines)
