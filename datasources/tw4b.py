# -*- coding: utf-8 -*-
"""
Created on Wed Jul  6 11:22:48 2016

@author: terahertz
"""

from common import DataSource
import asyncio
import logging
import socket
import struct
import io


class TW4BException(Exception):
    pass


class TW4BClientProtocol:
    def __init__(self, new_system_discovered_cb=None, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.discovered_systems = {}
        self.transport = None
        def no_handler(ip, name): pass
        self.new_system_discovered_cb = new_system_discovered_cb or no_handler

    def connection_made(self, transport):
        logging.info("TW4B Broadcast Receiver: Listening for devices.")
        self.transport = transport

    def datagram_received(self, data, addr):
        (ip, name) = data.decode().split('\r')
        ip = ip.split(' ')[1]
        if ip not in self.discovered_systems:
            self.discovered_systems[ip] = name
            self.new_system_discovered_cb(ip, name)

    def error_received(self, exc):
        logging.error(exc)

    def connection_lost(self, exc):
        logging.warning(exc)


def _status2dict(status):
    status = io.StringIO(status)
    name = status.readline()
    statusdict = {}

    for line in status:
        line = line.strip()
        k, v = line.split(':')
        k = k.strip()
        v = v.strip()
        statusdict[k] = v

    return name, statusdict


class TW4B(DataSource):

    discoverer = None

    def __init__(self, name_or_ip=None, objectName=None, loop=None):
        super().__init__(objectName, loop)

        systems = self.discovered_systems()
        if not systems:
            raise Exception("No TW4B compatible devices found")

        if name_or_ip is None:
            self.ip = next(iter(systems.keys()))
        else:
            self.ip = None

            try:
                socket.inet_aton(name_or_ip)
                self.ip = name_or_ip
            except OSError:
                matches = ([ip for ip, name in systems.items()
                            if name == name_or_ip])
                if matches:
                    self.ip = matches[0]

        if not self.ip:
            raise Exception("No suitable device found for identifier {}"
                            .format(name_or_ip))


    def send_command(self, command):
        # magic bytes, always the same
        magic = bytes.fromhex('CDEF1234789AFEDC0000000200000000')
        encoded_length = struct.pack('>I', len(command))
        command = magic + encoded_length + command.encode('ascii')

        self.control_writer.write(command)


    async def read_message(self):
        header = await self.control_reader.read(20)
        magic1, magic2, code, timestamp, length = struct.unpack('>IIIII',
                                                                header)
        msg = await self.control_reader.read(length)
        return msg.decode('ascii')


    async def query(self, command):
        self.send_command(command)
        return await self.read_message()


    async def initialize(self):
        self.control_reader, self.control_writer = \
            await asyncio.open_connection(host=self.ip, port=6341,
                                          loop=self._loop)

        self.data_reader, _ = await asyncio.open_connection(host=self.ip,
                                                            port=6342,
                                                            loop=self._loop)

        ok = await self.read_message()
        if ok != 'OK':
            raise TW4BException("Initialization failed")

        print(await self.query("SYSTEM : TELL STATUS"))
        await self.query("SYSTEM : TIA FULL")

    @classmethod
    def discovered_systems(cls):
        return (None if cls.discoverer is None
                else cls.discoverer.discovered_systems)

    @classmethod
    async def start_device_discovery(cls, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        transport, cls.discoverer = await loop.create_datagram_endpoint(
            TW4BClientProtocol, local_addr=('0.0.0.0', 58432),
            reuse_address=True, allow_broadcast=True
        )

        return cls.discoverer


if __name__ == '__main__':

    async def setup():
        await TW4B.start_device_discovery()
        await asyncio.sleep(1)
        print(TW4B.discovered_systems())
        tflash = TW4B()
        print(tflash.ip)
        await tflash.initialize()

    print("Running....")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup())
