# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 09:14:38 2015

@author: Arno Rehn
"""

from common import ComponentBase
from asyncioext.asyncserial import Serial

class Connection(ComponentBase):
    def __init__(self, port = None, baudRate = 9600):
        super().__init__()
        self.port = port
        self.baudRate = baudRate
        self.serial = Serial()

    def __del__(self):
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

    async def send(self, command, *args):
        """ Send a command over the Connection. If the command is a request,
        returns the reply.

        Parameters
        ----------
        command (convertible to bytearray) : The command to be sent.
        """

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

        # read reply. lines ending with ' \n' are part of a multiline reply.
        replyLines = []
        while len(replyLines) == 0 or replyLines[-1][-2:] == ' \n':
            replyLines.append(await self.serial.async_readline())

        return b''.join(replyLines)
