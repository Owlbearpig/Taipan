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

from common import DataSource, Manipulator, DataSet
from common.components import action
import asyncio
import numpy as np
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from asyncioext import ensure_weakly_binding_future
from pint import Quantity
from traitlets import Instance, Bool


class DummyManipulator(Manipulator):
    isReferenced = Bool(False, read_only=True).tag(name="Is referenced")

    def __init__(self):
        super().__init__()
        self.set_trait('status', Manipulator.Status.Idle)
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)
        self.velocity = Q_(1, 'mm/s')
        self.set_trait('value', Q_(0, 'mm'))
        self._start = Q_(1, 'ps')
        self._stop = Q_(100, 'ps')
        self._step = Q_(0.005, 'ps')
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

    async def moveTo(self, val, velocity=None):
        if velocity is None:
            velocity = self.velocity

        velocity = velocity.to('mm/s').magnitude
        val = val.to('mm').magnitude
        curVal = self.value.to('mm').magnitude

        values = np.linspace(curVal, val, 50)
        dt = abs(np.mean(np.diff(values)) / velocity)

        self.set_trait('status', Manipulator.Status.Moving)

        try:
            for target in values:
                await asyncio.sleep(0.2)  # more realistic
                self.set_trait('value', Q_(target, 'mm'))
            #self._isMovingFuture = asyncio.Future()
            #await self._isMovingFuture
        finally:
            self.set_trait('status', Manipulator.Status.Idle)

    async def __aenter__(self):
        await super().__aenter__()
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)

        return self

    async def updateStatus(self):
        while True:
            await asyncio.sleep(2)
            #print(f"hello from {self.objectName}")
            await self.singleUpdate()

    async def singleUpdate(self):
        movFut = self._isMovingFuture

        if not movFut.done():
            # check if move done
            movFut.set_result(None)

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()

    async def waitForTargetReached(self):
        return await self._isMovingFuture

    @action("Reference stage")
    async def reference_stage(self):
        await asyncio.sleep(3)
        self.set_trait('isReferenced', True)


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


class DummyContinuousDataSource(DataSource):
    currentData = DataSetTrait(read_only=True, axes_labels=['foo'],
                               data_label='bar')

    def __init__(self, manip):
        super().__init__()
        self.manip = manip

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

    async def update_live_data(self):
        i = 0
        while True:
            taxis = np.arange(0, 10, 0.02) * ureg.ps
            omega = 2 * np.pi * ureg.THz
            data = np.sin(omega * (taxis + (i * 0.1) * ureg.ps))
            data += 5e-3 * (np.random.random(data.shape) - 0.5) * np.max(data)
            data = data * ureg.nA

            self.set_trait("currentData", DataSet(data, [taxis]))

            await asyncio.sleep(0.10, loop=self._loop)
            i = i + 1

    async def readDataSet(self):
        await asyncio.sleep(0.1)

        taxis = np.arange(self.manip._start.magnitude,
                          self.manip._stop.magnitude,
                          self.manip._step.magnitude) * self.manip._step.units
        omega = 2 * np.pi * ureg.THz
        data = np.sin(omega * taxis)
        data += 5e-3 * (np.random.random(data.shape) - 0.5) * np.max(data)
        data = data * ureg.nA

        dataSet = DataSet(data, [taxis])

        self._dataSetReady(dataSet)
        self.set_trait("currentData", DataSet(data, [taxis]))

        return dataSet
