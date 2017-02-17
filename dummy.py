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

from common import DataSource, Manipulator, DataSet
import asyncio
import numpy as np
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from asyncioext import ensure_weakly_binding_future


class DummyManipulator(Manipulator):

    def __init__(self):
        super().__init__()
        self.set_trait('status', Manipulator.Status.Idle)

        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.second)
        self.velocity = Q_(1, 'mm/s')
        self.set_trait('value', Q_(0, 'mm'))

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
                await asyncio.sleep(dt)
                self.set_trait('value', Q_(target, 'mm'))
        finally:
            self.set_trait('status', Manipulator.Status.Idle)

    async def configureTrigger(self, step, start=None, stop=None):
        self._step = step
        self._start = start
        self._stop = stop
        return step, start, stop


class DummySimpleDataSource(DataSource):

    def __init__(self, init=0):
        super().__init__()
        self.init = init
        self.stop()

    def stop(self):
        self.counter = self.init

    async def readDataSet(self):
        dataSet = DataSet(np.array(self.counter)*ureg.nA, [])
        self.counter += 1
        return dataSet


class DummyContinuousDataSource(DataSource):

    def __init__(self):
        super().__init__()

    TAU = 0.15

    @classmethod
    def thz_pulse(cls, t):
        return t * np.exp(-np.power(t/cls.TAU, 2))

    async def start(self, scanAxis=None):
        self._nextAxis = scanAxis

    async def readDataSet(self):
        taxis = self._nextAxis
        omega = 2 * np.pi * 3 / taxis.units

        data = self.thz_pulse(taxis - 220 * taxis.units)
        data += 5e-3 * (np.random.random(data.shape) - 0.5) * np.max(data)
        data = data * ureg.nA
        dataSet = DataSet(data, [taxis])
        return dataSet
