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
import logging
import time

from common import DataSource, Manipulator, DataSet, Scan
from common.components import action
import asyncio
import numpy as np
import enum
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from common.traits import Quantity
from asyncioext import ensure_weakly_binding_future
# from pint import Quantity
from traitlets import Instance, Bool, Enum, Int, List, Unicode
import warnings
from functools import partial


class DummySerial:
    # does nothing
    def __init__(self, *args, **kwargs):
        pass

    def isOpen(self, *args):
        return

    def open(self, *args):
        return

    def close(self, *args):
        return

    def write(self, message):
        print(message)

    def readline(self, *args):
        return b""

    def read(self, *args):
        return b""

    def flush(self, *args):
        pass

class DummyManipulator(Manipulator):
    isReferenced = Bool(False, read_only=True).tag(name="Is referenced")

    targetValue = Quantity(Q_(0, 'mm'), min=Q_(0, 'mm'), max=Q_(2047, 'mm')).tag(
        name='Target value')

    status_ = Unicode(str(Manipulator.Status.Undefined.name), read_only=True).tag(name="Status")

    def __init__(self):
        super().__init__()
        self.set_trait('status', Manipulator.Status.Idle)
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)
        self.velocity = Q_(10, 'mm/s')
        self.set_trait('value', Q_(0, 'mm'))
        self._start = Quantity(Q_(1, 'ps'))
        self._stop = Q_(100, 'ps')
        self._step = Q_(0.05, 'ps')
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)
        self._triggered_datasources = []

    def connect_trigger(self, datasource):
        # simulated triggering
        self._triggered_datasources.append(datasource)

    async def moveTo(self, val, velocity=None):
        if velocity is None:
            velocity = self.velocity

        velocity = velocity.to('mm/s').magnitude
        val = val.to('mm').magnitude
        curVal = self.value.to('mm').magnitude

        values = np.linspace(curVal, val, 2000)

        dt = abs(np.mean(np.diff(values)) / velocity)

        self.set_trait('status', Manipulator.Status.Moving)

        try:
            for target in values:
                await asyncio.sleep(dt)  # more realistic
                self.set_trait('value', Q_(target, 'mm'))
            self._isMovingFuture = asyncio.Future()
            await self._isMovingFuture
        finally:
            self.set_trait('status', Manipulator.Status.Idle)

    async def __aenter__(self):
        await super().__aenter__()
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)

        return self

    async def updateStatus(self):
        while True:
            await asyncio.sleep(0.2)
            await self.singleUpdate()

    async def singleUpdate(self):
        movFut = self._isMovingFuture

        self.set_trait("status_", self.status.name)

        if not movFut.done():
            # check if move done
            movFut.set_result(None)

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()
        await self._isMovingFuture

    async def waitForTargetReached(self):
        return await self._isMovingFuture

    @action("Reference stage")
    async def reference_stage(self):
        await asyncio.sleep(1)
        self.set_trait('isReferenced', True)

    async def _trigger(self, axis):
        axis = axis.to("mm")

        if axis[-1] < axis[0]:
            axis = axis[::-1]

        while True:
            await asyncio.sleep(0.01)
            if axis[0] <= self.value:
                # logging.info(f"triggered {axis[0]}, {self.value}")
                axis = axis[1:]
                for datasource in self._triggered_datasources:
                    await datasource.acquire_point()
                if len(axis) == 0:
                    break

    async def configureTrigger(self, axis):
        trigger_inst = partial(self._trigger, axis=axis)
        asyncio.ensure_future(trigger_inst())

        return axis


class DummySimpleDataSource(DataSource):

    def __init__(self, init=0):
        super().__init__()
        self.init = init

    async def stop(self):
        self.counter = self.init

    async def readDataSet(self):
        dataSet = DataSet(np.array(self.counter) * ureg.nA, [])
        self.counter += 1
        return dataSet


class DummyLockIn(DataSource):
    class SamplingMode(enum.Enum):
        SingleShot = 0
        Buffered = 1
        ### TODO: support me!
        # Fast = 2

    samplingMode = Enum(SamplingMode, SamplingMode.Buffered).tag(
        name="Sampling mode")

    samplePeriod = Quantity(Q_(0.2, "ps")).tag(name="Sampling period")

    bufferLength = Int(default_value=20000).tag(name="Buffer Length",
                                                group='Data Curve Buffer')
    pointsInBuffer = Int(default_value=0, read_only=True).tag(name="Points in buffer",
                                                              group='Data Curve Buffer')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._signalUpdateFuture = ensure_weakly_binding_future(self.dummy_signal)
        self._updateFuture = ensure_weakly_binding_future(self.update)
        self._data_buffer = []
        self._sim_signal_buffer = []
        self._acquisition_en = False
        self._trigger_positions = None

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._signalUpdateFuture.cancel()
        self._updateFuture.cancel()

    async def update(self):
        while True:
            await asyncio.sleep(0.1)
            self.set_trait("pointsInBuffer", len(self._data_buffer))

    async def dummy_signal(self):
        sampling_period = self.samplePeriod.magnitude

        async def signal(time_):
            amp, freq = 1.0, 1.0
            amp_noise = np.random.random()
            amp *= amp_noise

            x = amp * np.sin(freq * sampling_period * time_)
            y = amp * np.sin(freq * sampling_period * time_ + np.pi / 2)
            r = x ** 2 + y ** 2
            theta = np.angle(x + 1j * y)

            channels_ = [x, y, r, theta]

            return channels_

        time_ = 0
        while True:
            await asyncio.sleep(0.1)
            if not self._acquisition_en:
                continue

            if len(self._sim_signal_buffer) >= self.bufferLength:
                self._sim_signal_buffer = []
                time_ = 0

            channels = await signal(time_)
            self._sim_signal_buffer.append(channels)
            time_ += 1

    async def query(self, cmd):
        channels = self._sim_signal_buffer[-1]
        if cmd == 'OUTP? 1':
            return channels[0]
        elif cmd == 'OUTP? 2':
            return channels[1]
        elif cmd == 'OUTP? 3':
            return channels[2]
        elif cmd == 'OUTP? 4':
            return channels[3]

    async def readCurrentOutput(self, channel='X'):
        try:
            idx = ['x', 'y', 'r', 'theta'].index(channel.lower()) + 1
        except ValueError:
            raise ValueError("'{}' is not a valid channel identifier. "
                             "Valid values are: 'x', 'y', 'r', 'theta'."
                             .format(channel))

        return await self.query('OUTP? %d' % idx)

    async def acquire_point(self):
        self._data_buffer.append(await self.readCurrentOutput())

    async def start(self, scanAxis=None):
        self._acquisition_en = True
        self._trigger_positions = scanAxis

    async def stop(self):
        self._acquisition_en = False

    async def read_buffer(self):
        buffer = np.array(self._data_buffer).copy()
        self._data_buffer = []

        return buffer

    async def readDataSet(self):
        if self.samplingMode == DummyLockIn.SamplingMode.SingleShot:
            data = np.array(await self.readCurrentOutput())
            dataSet = DataSet(Q_(data), [])
            self._dataSetReady(dataSet)
            return dataSet
        elif self.samplingMode == DummyLockIn.SamplingMode.Buffered:
            data = await self.read_buffer()
            dataSet = DataSet(Q_(data), [self._trigger_positions.to("ps")])
            self._dataSetReady(dataSet)
            return dataSet

    @action("Dump buffer")
    def dump_buffer(self):
        if not self._data_buffer:
            logging.info("Buffer empty")
            return

        async def _impl():
            dataset = await self.readDataSet()
            self.set_trait("currentData", dataset)

        self._loop.create_task(_impl())

    @action("Acquire signal")
    def start_acq(self):
        self._loop.create_task((self.start()))


class DummyContinuousDataSource(DataSource):
    currentData = DataSetTrait(read_only=True, axes_labels=['foo'],
                               data_label='bar')

    acq_begin = Quantity(Q_(500, 'ps')).tag(name="Start", priority=0)
    acq_range = Quantity(Q_(10, 'ps')).tag(name="Range", priority=1)
    acq_on = Bool(False, read_only=True).tag(name="Acquistion active")

    def __init__(self, freq=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._acq_future = None
        self.freq = freq

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

    async def update_live_data(self):
        dt = 0.05
        taxis = dt * np.arange(self.acq_range.magnitude / dt) + self.acq_begin.magnitude
        freq = 0.5 + np.random.random()  # freq between 0.5 and 1.5 (THz)
        if self.freq is not None:
            freq = self.freq
        while self.acq_on:
            omega = 2 * np.pi * freq * ureg.THz
            data = np.sin(omega * taxis * ureg.ps)
            data += 5e-3 * (np.random.random(data.shape) - 0.5) * np.max(data)
            data = data * ureg.nA

            self.set_trait("currentData", DataSet(data, [Q_(taxis, 'ps')]))
            self._dataSetReady(self.currentData)

            await asyncio.sleep(0.50)

    async def start(self):
        self.start_acq()

    async def stop(self):
        self.stop_acq()

    @action("Start acquisition")
    def start_acq(self):
        async def _impl():
            await self.update_live_data()
            # await self.reset_avg()

        self.set_trait('acq_on', True)
        self._loop.create_task(_impl())

    @action("Stop acquisition")
    def stop_acq(self):
        if self.acq_on:
            self.set_trait('acq_on', False)

    async def readDataSet(self):
        self._dataSetReady(self.currentData)

        return self.currentData


class DummyDoubleDatasource(DummyContinuousDataSource):
    currentData2 = DataSetTrait(read_only=True, axes_labels=['foo'],
                                data_label='bar')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def update_live_data(self):
        dt = 0.05
        taxis = dt * np.arange(self.acq_range.magnitude / dt) + self.acq_begin.magnitude
        while self.acq_on:
            omega = 2 * np.pi * ureg.THz
            data = np.sin(omega * taxis * ureg.ps)
            data += 5e-3 * (np.random.random(data.shape) - 0.5) * np.max(data)
            data = data * ureg.nA

            self.set_trait("currentData", DataSet(data, [Q_(taxis, 'ps')]))
            self.set_trait("currentData2", DataSet(data, [Q_(taxis, 'ps')]))

            await asyncio.sleep(0.10)
