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

import asyncio
from common import DataSet, DataSource, Q_, action
from asyncioext import ensure_weakly_binding_future
from asyncioext.aioserial import create_serial_connection
from threading import Lock
import re
from serial import aio as aioserial
from serial.threaded import Packetizer, LineReader
import logging
from traitlets import Bool, Enum, Int, observe
import enum
from multiprocessing import Process, Queue
import struct
import binascii
import numpy as np
from common.traits import DataSet as DataSetTrait, Quantity
import time

_replyExpression = re.compile(r'([a-zA-Z0-9]+)=\s*(-?[0-9]+)')


class PulseReader(Packetizer):
    TERMINATOR = b'\r'

    pulse = b''

    def __init__(self, q):
        super().__init__()
        self.q = q

    def handle_packet(self, packet):
        self.pulse += packet
        if self.pulse.endswith(b'X') or self.pulse.endswith(b'Y'):
            self.handle_hex_pulse(self.pulse[:-1])
            self.pulse = b''

    def handle_hex_pulse(self, hexPulse):
        rawPulse = binascii.a2b_hex(hexPulse)
        pulse = struct.unpack('>{}h'.format(int(len(rawPulse) / 2)), rawPulse)
        pulse = np.array(pulse, dtype=float)
        self.q.put(pulse)


def read_pulse_data(port, q):
    loop = asyncio.new_event_loop()

    coro = create_serial_connection(loop, lambda: PulseReader(q),
                                              port, baudrate=115200)

    loop.run_until_complete(coro)
    loop.run_forever()


_dt = 4.36968965E-15 * 1e12


def _counts2ps(x):
    return Q_(x * _dt, 'ps')


def _ps2counts(x):
    return int(x.to('ps').magnitude / _dt)


def _millivolts2volts(x):
    return Q_(x / 1000, 'V')


def _volts2millivolts(x):
    return int(x.to('V').magnitude * 1000)


class TEMFiberStretcher(DataSource):
    @enum.unique
    class Averages(enum.Enum):
        Avg_1 = 0
        Avg_2 = 1
        Avg_4 = 2
        Avg_8 = 3
        Avg_16 = 4
        Avg_32 = 5
        Avg_64 = 6
        Avg_128 = 7

    _lineReader = None

    handlers = []

    _blockObserver = False

    neglectFirstDataSet = Bool(False, read_only=False).tag(
        name="Neglect First Dataset",
        group="Data acquisition")

    measurementRate = Quantity(Q_(0, 'Hz'), read_only=True).tag(
        name="Rate",
        group="Data acquisition")
    recStart = Quantity(Q_(0, 'ps')).tag(name="Start",
                                         i2q=_counts2ps, q2i=_ps2counts,
                                         priority=0, group="Data acquisition")
    recStop = Quantity(Q_(0, 'ps')).tag(name="Stop",
                                        i2q=_counts2ps, q2i=_ps2counts,
                                        priority=1, group="Data acquisition")
    recInterval = Quantity(Q_(0, 'ps')).tag(name="Step",
                                            i2q=_counts2ps, q2i=_ps2counts,
                                            priority=2, group="Data acquisition")
    average = Enum(Averages, Averages.Avg_1).tag(name="Averages",
                                                 group="Data acquisition")
    measurement = Bool(False).tag(name="Record data",
                                  group="Data acquisition")
    risingOnly = Bool(True).tag(name="Rising only", group="Data acquisition")

    mTarget = Int(0).tag(name="Motor target position", group="Stepper motor")
    mScanEnable = Bool(False).tag(name="Motor scan active",
                                  group="Stepper motor")
    mSpeedMax = Int(0).tag(name="Maximum speed", group="Stepper motor")
    mSpeedMin = Int(0).tag(name="Minimum speed", group="Stepper motor")

    scanRecStart = Int(0).tag(name="Start", group="Piezo scan")
    scanOffset = Quantity(Q_(0, 'V'), min=Q_(-5, 'V'), max=Q_(5, 'V')).tag(
        name="Offset", group="Piezo scan",
        i2q=_millivolts2volts,
        q2i=_volts2millivolts)
    scanFrequency = Int(0).tag(name="Frequency", group="Piezo scan")
    scanAmpl = Int(0).tag(name="Amplitude", group="Piezo scan")
    scanEnable = Bool(False).tag(name="Piezo scan active", group="Piezo scan")

    dcValue = Quantity(Q_(0, 'V')).tag(name="DC Voltage",
                                       i2q=_millivolts2volts,
                                       q2i=_volts2millivolts,
                                       group="Emitter Voltage")
    dcOut = Bool(False).tag(name="DC output active", group="Emitter Voltage")

    currentData = DataSetTrait(read_only=True).tag(name="Live data",
                                                   data_label="Amplitude",
                                                   axes_labels=["Time"])

    _lastDataTime = 0

    def __init__(self, controlPort, dataPort, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self.controlPort = controlPort
        self.dataPort = dataPort
        self.commLock = Lock()

        self.handlers.append(self.update_handler)

        self.newDataReady = asyncio.Future()

    _traitVars = ['recStart', 'recStop', 'average', 'mScanEnable', 'mTarget',
                  'mSpeedMax', 'mSpeedMin', 'scanEnable', 'measurement',
                  'risingOnly', 'recInterval', 'dcOut', 'dcValue',
                  'scanRecStart', 'scanOffset', 'scanAmpl', 'scanFrequency']

    @observe(*_traitVars)
    def observer(self, change):
        logging.info("TEMFS: Trait change '{x[name]}' = {x[new]}"
                     .format(x=change))
        if self._blockObserver:
            return

        val = change['new']

        trait = self.traits()[change['name']]
        if isinstance(trait, Quantity):
            val = trait.metadata.get('q2i')(val)
        if isinstance(trait, Enum):
            val = val.value

        self.setVar(change['name'], val)

    @classmethod
    def _sanitizeCommand(cls, cmd):
        cmd = cmd.lower()
        return cmd

    async def query(self, var):
        self.send(var + '=')
        reply = await self.expect_single(r'^{}=\s*([0-9]+)'.format(var),
                                         re.IGNORECASE)
        val = int(reply.groups()[0])
        return val

    def update_handler(self, line):
        match = _replyExpression.match(line)
        if not match:
            return

        var = match.groups()[0]
        val = int(match.groups()[1])

        possibleTraits = [trait for name, trait in self.traits().items()
                          if name.lower() == var.lower()]
        if not possibleTraits:
            logging.info("TEMFiberStretcher: Got update for variable {}={} "
                         "but no trait with a matching name."
                         .format(var, val))
            return

        trait = possibleTraits[0]
        self._blockObserver = True
        try:
            if isinstance(trait, Quantity):
                val = int(val)
                val = trait.metadata.get('i2q')(val)
            else:
                traitType = type(trait.get(self))
                val = traitType(val)

            trait.set(self, val)
        finally:
            self._blockObserver = False

    def expect_single(self, expect, flags=0):
        fut = asyncio.Future(loop=self._loop)

        def predicate(x):
            match = re.match(expect, x, flags=flags)
            if match:
                fut.set_result(match)
                self.handlers.remove(predicate)

        self.handlers.append(predicate)
        return fut

    def setVar(self, var, value):
        value = int(value)
        self.send('{}={}'.format(var, value))

    def send(self, command):
        command = self._sanitizeCommand(command)
        logging.info("TEMFS:SEND: {}".format(command))
        self._lineReader.write_line(command)

    def handle_line(self, line):
        logging.info("TEMFS:HANDLING {}".format(line))

        for x in self.handlers:
            x(line)

    def handle_error(self, error):
        print(error)

    @observe("currentData")
    def currentDataChanged(self, change):
        assert (not self.newDataReady.done()), \
            "newDataReady Future should never be done at this stage!"

        t = time.perf_counter()
        rate = 1.0 / (t - self._lastDataTime)
        self._lastDataTime = t
        self.set_trait('measurementRate', Q_(rate, 'Hz'))

        # ensure that callbacks/coroutines only run after we've set a new
        # asyncio.Future
        fut = self.newDataReady
        self.newDataReady = asyncio.Future()
        fut.set_result(change['new'])

    async def readDataSet(self):
        if self.neglectFirstDataSet:
            await self.newDataReady
        dataSet = await self.newDataReady
        self._dataSetReady(dataSet)
        return dataSet

    async def readPulseFromQueue(self):
        while True:
            # yield control to the event loop once
            await asyncio.sleep(0)

            while not self._pulseQueue.empty():
                pulse = self._pulseQueue.get()
                pulse = Q_(pulse)

                axis = (self.recStart + np.arange(len(pulse)) *
                        self.recInterval)
                axis = Q_(axis, 'ps')

                data = DataSet(pulse, [axis])

                self.set_trait('currentData', data)

    @action("Reset counter", group="Data acquisition")
    def resetCounter(self):
        self.send("ResetCounter")

    async def __aenter__(self):
        await super().__aenter__()

        self._controlTransport, self._lineReader = \
            await aioserial.create_serial_connection(self._loop, LineReader,
                                                     self.controlPort,
                                                     baudrate=57600)
        self._lineReader.handle_line = self.handle_line
        await asyncio.sleep(0)

        for var in self._traitVars:
            self.send(var + "=")

        self.mScanEnable = False
        self.scanEnable = False
        self.measurement = True
        self.dcOut = True

        self._pulseQueue = Queue()
        self._pulseReader = Process(target=read_pulse_data,
                                    args=(self.dataPort, self._pulseQueue))
        self._pulseReader.start()
        self._pulseFromQueueReader = \
            ensure_weakly_binding_future(self.readPulseFromQueue)

        return self

    async def __aexit__(self, *args):
        self.dcOut = False
        self.measurement = False
        self.mScanEnable = False
        self.scanEnable = False
        self._pulseFromQueueReader.cancel()
        await asyncio.sleep(1)
        self._pulseReader.terminate()
        await super().__aexit__(*args)


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)

    loop = asyncio.get_event_loop()
    print(id(loop))


    async def run():
        async with TEMFiberStretcher('/tmp/fiberstretcher0', '/tmp/fiberstretcher1', loop=loop) as fs:
            fs.dcValue = 8000
            fs.recStart = 1000
            fs.recStop = 10000
            fs.recInterval = 30
            await asyncio.sleep(2)
            fs.risingOnly = False
            fs.measurement = True
            fs.mScanEnable = True
            await asyncio.sleep(5)
            fs.measurement = False
            await asyncio.sleep(2)


    loop.run_until_complete(run())

#    print(fs.send('hello'))
#    print(fs.query('RecInterval'))

#    reply = 'RecInterval asd= 20'
#    match = _replyExpression.match(reply)
#    assert match, 'failed'
#
