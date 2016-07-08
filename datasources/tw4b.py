# -*- coding: utf-8 -*-
"""
Created on Wed Jul  6 11:22:48 2016

@author: terahertz
"""

from common import DataSet, DataSource, Q_, action
import asyncio
from asyncioext import ensure_weakly_binding_future
import logging
import socket
import struct
import io
from common.traits import Quantity, DataSet as DataSetTrait
from traitlets import Bool, Float, Unicode, observe, Integer
import numpy as np
import traceback

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
    name = status.readline().strip()
    statusdict = {}

    for line in status:
        line = line.strip()
        k, v = line.split(':')
        k = k.strip()
        v = v.strip()
        statusdict[k] = v

    return name, statusdict


def _fix2float(v, bits=16):
    mask = 0xFFFFFFFF >> (32 - bits)
    return (v >> bits) + (v & mask) / mask


_magicScale = 5.9605E-10


class TW4B(DataSource):

    discoverer = None

    busy = Bool(False, read_only=True)
    acq_begin = Quantity(Q_(500, 'ps'))
    acq_range = Quantity(Q_(70, 'ps'))
    acq_on = Bool(False, read_only=True)
    acq_avg = Integer(1, min=1, max=30000)
    acq_current_avg = Integer(0, read_only=True)
    laser_on = Bool(False)
    laser_set = Float(50.0, min=0, max=100)
    system_status = Unicode('Undefined', read_only=True)
    serial_number = Unicode('Undefined', read_only=True)
    identification = Unicode('Undefined', read_only=True)
    firmware_version = Unicode('Undefined', read_only=True)

    currentData = DataSetTrait(read_only=True)

    def __init__(self, name_or_ip=None, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self._traitChangesDueToStatusUpdate = False
        self.ip = None
        self._commlock = asyncio.Lock()

        try:
            socket.inet_aton(name_or_ip)
            self.ip = name_or_ip
        except OSError:
            pass

        if self.ip is None:
            systems = self.discovered_systems()
            if not systems:
                raise Exception("No TW4B compatible devices found")

            if name_or_ip is None:
                self.ip = next(iter(systems.keys()))
            else:
                matches = ([ip for ip, name in systems.items()
                            if name == name_or_ip])
                if matches:
                    self.ip = matches[0]

        if self.ip is None:
            raise Exception("No suitable device found for identifier {}"
                            .format(name_or_ip))

        self._statusUpdater = None
        self._pulseReader = None

    def send_command(self, command):
        # magic bytes, always the same
        magic = bytes.fromhex('CDEF1234789AFEDC0000000200000000')
        encoded_length = struct.pack('>I', len(command))
        command = magic + encoded_length + command.encode('ascii')

        self.control_writer.write(command)
        self.set_trait('busy', True)

    expected_magic1 = 0xCDEF1234
    expected_magic2 = 0x789AFEDC

    async def read_pulse_data(self):
        while True:
            header = await self.data_reader.readexactly(36)
            (magic1, magic2, code, timestamp, tiasens, begin, resolution,
             amplitude, length) = struct.unpack('>IIIIIIIII', header)

            if (magic1 != self.expected_magic1 or
                magic2 != self.expected_magic2):
                logging.warning("Corrupted pulse received! "
                                "Buffer overrun?")
                continue

            pulsedata = await self.data_reader.readexactly(length)
            pulse = np.array(struct.unpack('>{}i'.format(int(length / 4)),
                                           pulsedata), dtype=float)
            pulse *= _magicScale * _fix2float(tiasens)
            pulse = Q_(pulse, 'nA')

            start_ps = _fix2float(begin)
            axis = np.arange(len(pulse)) * 0.05 + start_ps
            axis = Q_(axis, 'ps')

            data = DataSet(pulse, [axis])

            self.set_trait('currentData', data)
            self.set_trait('acq_current_avg', min(self.acq_current_avg + 1, self.acq_avg))


    async def read_message(self):
        async with self._commlock:
            header = await self.control_reader.readexactly(20)
            magic1, magic2, code, timestamp, length = struct.unpack('>IIIII',
                                                                    header)
            msg = await self.control_reader.readexactly(length)
            self.set_trait('busy', False)
            return msg.decode('ascii')

    async def query(self, command):
        self.send_command(command)
        return await self.read_message()

    async def updateStatus(self):
        while True:
            await asyncio.sleep(0.2)
            await self.singleUpdate()

    async def singleUpdate(self):
        ident, status = _status2dict(await self.query("SYSTEM : TELL STATUS"))

        self._traitChangesDueToStatusUpdate = True
        self.set_trait('identification', ident)
        self.set_trait('serial_number', status['Ser.No'])
        self.set_trait('system_status', status['System'])
        self.set_trait('firmware_version', status['Firmware'])
        self.set_trait('laser_on', status['Laser'] == 'ON')
        self.set_trait('laser_set', float(status['Laser-Set']))
        self.set_trait('acq_on', status['Acquisition'] == 'ON')
        self.set_trait('acq_range', Q_(float(status['Acq-Range/ps']), 'ps'))
#        self.set_trait('acq_begin', Q_(float(status['Acq-Begin/ps']), 'ps'))
        self._traitChangesDueToStatusUpdate = False

    @observe('laser_on')
    def laser_on_changed(self, change):
        if self._traitChangesDueToStatusUpdate:
            return

        if change['new']:
            self._loop.create_task(self.query('LASER : ON'))
        else:
            self._loop.create_task(self.query('LASER : OFF'))

    @observe('acq_begin')
    def acq_begin_changed(self, change):
        if self._traitChangesDueToStatusUpdate:
            return

        newVal = change['new'].to('ps').magnitude
        self._loop.create_task(
            self.query('ACQUISITION : BEGIN {}'.format(newVal))
        )

    @observe('acq_range')
    def acq_range_changed(self, change):
        if self._traitChangesDueToStatusUpdate:
            return

        newVal = int(change['new'].to('ps').magnitude)
        self._loop.create_task(
            self.query('ACQUISITION : RANGE {}'.format(newVal))
        )

    @observe('acq_avg')
    def acq_avg_changed(self, change):
        print("average to {}".format(change['new']))
        self._loop.create_task(
            self.query('ACQUISITION : AVERAGE {}'.format(int(change['new'])))
        )

    @action("Start acquisition")
    def start(self):
        self._loop.create_task(self.query('ACQUISITION : START'))

    @action("Stop acquisition")
    def stop(self):
        self._loop.create_task(self.query('ACQUISITION : STOP'))

    @action("Reset average")
    def reset_avg(self):
        self._loop.create_task(self.query('ACQUISITION : RESET AVG'))
        self.set_trait('acq_current_avg', 0)

    async def __aenter__(self):
        print("Initializing TW4B...")

        self.control_reader, self.control_writer = \
            await asyncio.open_connection(host=self.ip, port=6341,
                                          loop=self._loop)

        self.data_reader, self.data_writer = \
            await asyncio.open_connection(host=self.ip, port=6342,
                                          loop=self._loop)

        ok = await self.read_message()
        if ok != 'OK':
            raise TW4BException("Initialization failed")

        await self.singleUpdate()
        self._statusUpdater = ensure_weakly_binding_future(self.updateStatus)
        self._pulseReader = ensure_weakly_binding_future(self.read_pulse_data)

        return self

    async def __aexit__(self, *args):
        print("closing tw4b")
        await super().__aexit__(*args)

        self._statusUpdater.cancel()
        self._pulseReader.cancel()

        self.control_writer.close()
        self.data_writer.close()

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
