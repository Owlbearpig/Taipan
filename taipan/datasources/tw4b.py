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
from threading import Thread
from multiprocessing import Process, Queue


class TW4BException(Exception):
    pass


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


def read_pulse_data(ip, q):
    loop = asyncio.new_event_loop()

    data_reader, data_writer = \
        loop.run_until_complete(
            asyncio.open_connection(host=ip, port=6342, loop=loop))

    expected_magic1 = 0xCDEF1234
    expected_magic2 = 0x789AFEDC

    async def _impl():
        while True:
            header = await data_reader.readexactly(36)
            (magic1, magic2, code, timestamp, tiasens, begin, resolution,
             amplitude, length) = struct.unpack('>IIIIIIIII', header)

            if (magic1 != expected_magic1 or
                magic2 != expected_magic2):
                logging.warning("Corrupted pulse received! "
                                "Buffer overrun?")
                continue

            pulsedata = await data_reader.readexactly(length)
            pulse = np.array(struct.unpack('>{}i'.format(int(length / 4)),
                                           pulsedata), dtype=int)
            pulse = _fix2float(pulse, 5).astype(float)
            pulse *= _magicScale * _fix2float(tiasens)
            q.put((pulse, begin))

    loop.run_until_complete(_impl())
    print("TW4B Data Reader quitting...")
    data_writer.close()
    q.close()
    loop.close()

class TW4B(DataSource):

    discoverer = None

    busy = Bool(False, read_only=True).tag(name="Busy")
    acq_begin = Quantity(Q_(500, 'ps')).tag(name="Start", priority=0)
    acq_range = Quantity(Q_(70, 'ps')).tag(name="Range", priority=1)
    acq_on = Bool(False, read_only=True).tag(name="Acquistion active")
    acq_avg = Integer(1, min=1, max=30000).tag(name="Averages", priority=2)
    acq_current_avg = Integer(0, read_only=True).tag(name="Current averages", priority=3)
    laser_on = Bool(False).tag(name="Laser on")
    laser_set = Float(50.0, min=0, max=100).tag(name="Laser set-point")
    system_status = Unicode('Undefined', read_only=True).tag(name="Status")
    serial_number = Unicode('Undefined', read_only=True).tag(name="Serial no.")
    identification = Unicode('Undefined', read_only=True).tag(name="Identification")
    firmware_version = Unicode('Undefined', read_only=True).tag(name="Firmware ver.")
    P2Pval = Unicode('Undefined',read_only=True).tag(name="P2P val")
    max_pos = Quantity(Q_(0, 'ps'), read_only=True).tag(name="Arg max")
    
    currentData = DataSetTrait(read_only=True).tag(name="Live data",
                                                   data_label="Amplitude",
                                                   axes_labels=["Time"])

    def __init__(self, name_or_ip=None, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self._traitChangesDueToStatusUpdate = False
        self.name_or_ip = name_or_ip
        self._commlock = asyncio.Lock()
        self._statusUpdater = None
        self._pulseReader = None
        self._setBusyFuture = None
        self._setAveragesReachedFuture = asyncio.Future()

    def send_command(self, command):
        # magic bytes, always the same
        magic = bytes.fromhex('CDEF1234789AFEDC0000000200000000')
        encoded_length = struct.pack('>I', len(command))
        command = magic + encoded_length + command.encode('ascii')

        self.control_writer.write(command)

        if self._setBusyFuture:
            self._setBusyFuture.cancel()
        self._setBusyFuture = self._loop.call_later(
                                  0.1, lambda: self.set_trait('busy', True))

    async def readPulseFromQueue(self):
        while True:
            # yield control to the event loop once
            await asyncio.sleep(0)

            while not self.pulseQueue.empty():
                pulse, begin = self.pulseQueue.get()
                offset = np.mean(pulse[:10])
                p2p=np.max(pulse)-np.min(pulse)
                self.set_trait('P2Pval', str(np.round(p2p, 3)))
                
                pulse = Q_(pulse-offset, 'nA')

                start_ps = _fix2float(begin)
                axis = np.arange(len(pulse)) * 0.05 + start_ps
                self.set_trait('max_pos', Q_(axis[np.argmax(pulse)], 'ps'))
                
                axis = Q_(axis, 'ps')

                data = DataSet(pulse, [axis])
                
                
                self.set_trait('currentData', data)
                self.set_trait('acq_current_avg', min(self.acq_current_avg + 1,
                                                      self.acq_avg))
                if (not self._setAveragesReachedFuture.done() and
                    self.acq_current_avg >= self.acq_avg):
                    self._setAveragesReachedFuture.set_result(True)

    async def read_message(self):
        async with self._commlock:
            header = await self.control_reader.readexactly(20)
            magic1, magic2, code, timestamp, length = struct.unpack('>IIIII',
                                                                    header)
            msg = await self.control_reader.readexactly(length)
            if self._setBusyFuture:
                self._setBusyFuture.cancel()
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

        async def _impl():
            await self.query('ACQUISITION : BEGIN {}'.format(newVal))
            await self.reset_avg()

        self._loop.create_task(_impl())

    @observe('acq_range')
    def acq_range_changed(self, change):
        if self._traitChangesDueToStatusUpdate:
            return

        newVal = int(change['new'].to('ps').magnitude)

        async def _impl():
            await self.query('ACQUISITION : RANGE {}'.format(newVal))
            await self.reset_avg()

        self._loop.create_task(_impl())

    @observe('acq_avg')
    def acq_avg_changed(self, change):
        self._loop.create_task(
            self.query('ACQUISITION : AVERAGE {}'.format(int(change['new'])))
        )

    @action("Start acquisition")
    def start_acq(self):
        async def _impl():
            await self.query('ACQUISITION : START')
            await self.reset_avg()
        self._loop.create_task(_impl())

    @action("Stop acquisition")
    def stop_acq(self):
        self._loop.create_task(self.query('ACQUISITION : STOP'))

    @action("Reset average")
    async def reset_avg(self):
        await self.query('ACQUISITION : RESET AVG')
        self.set_trait('acq_current_avg', 0)
        if self._setAveragesReachedFuture.done():
            self._setAveragesReachedFuture = asyncio.Future()
    
    async def device_init(self):
        print("Initializing TW4B...")

        self.ip = None

        try:
            if self.name_or_ip is not None:
                socket.inet_aton(self.name_or_ip)
                self.ip = self.name_or_ip
        except OSError:
            pass

        if self.ip is None:
            systems = self.discovered_systems
            if not systems:
                raise Exception("No TW4B compatible devices found")

            if self.name_or_ip is None:
                self.ip = next(iter(systems.keys()))
            else:
                matches = ([ip for ip, name in systems.items()
                            if name == self.name_or_ip])
                if matches:
                    self.ip = matches[0]

        if self.ip is None:
            raise Exception("No suitable device found for identifier {}"
                            .format(self.name_or_ip))

        self.control_reader, self.control_writer = \
            await asyncio.open_connection(host=self.ip, port=6341,
                                          loop=self._loop)

        self.pulseQueue = Queue()
        self.dataReaderProcess = Process(target=read_pulse_data,
                                         args=(self.ip, self.pulseQueue))
        self.dataReaderProcess.start()

        self.pulseReader = ensure_weakly_binding_future(self.readPulseFromQueue)
        
        ok = await self.read_message()
        
        if ok != 'OK':
            raise TW4BException("Initialization failed")
        
        await self.singleUpdate()
        self._statusUpdater = ensure_weakly_binding_future(self.updateStatus)
    
    async def __aenter__(self):
        retries = 10
        for i in range(1, retries):
            try:
                await self.device_init()
                break
            except asyncio.streams.IncompleteReadError:
                if i == retries-1:
                    raise TW4BException("Initialization failed")
                print(f"Initialization failed, retrying: {i}/{retries}")
                await asyncio.sleep(1)
        
        return self

    async def __aexit__(self, *args):
        print("closing tw4b")
        await super().__aexit__(*args)

        self.pulseReader.cancel()
        self._statusUpdater.cancel()
        self.dataReaderProcess.terminate()
        self.control_writer.close()

    async def readDataSet(self):
        if not self.acq_on:
            raise Exception("Trying to read data from TW4B but acquisition is "
                            "turned off!")

        await self.reset_avg()
        success = await self._setAveragesReachedFuture
        if not success:
            raise Exception("Failed to reach the target averages value!")

        self._dataSetReady(self.currentData)
        return self.currentData

    discovered_systems = {}

    @classmethod
    def start_device_discovery(cls, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        def recv_broadcast():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', 58432))
            s.settimeout(2)

            while not loop.is_closed():
                try:
                    data = s.recv(1024)
                except socket.timeout:
                    continue

                (ip, name) = data.decode().split('\r')
                ip = ip.split(' ')[1]
                if ip not in cls.discovered_systems:
                    cls.discovered_systems[ip] = name

        cls._discovererThread = Thread(target=recv_broadcast)
        cls._discovererThread.start()
