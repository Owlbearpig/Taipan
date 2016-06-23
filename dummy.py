# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 14:56:08 2015

@author: pumphaus
"""

from common import DataSource, Manipulator, DataSet, ComponentBase
import asyncio
import numpy as np
from traitlets import Instance
from common.units import Q_, ureg


class DummyManipulator(Manipulator):

    def __init__(self):
        super().__init__()
        self.set_trait('status', Manipulator.Status.TargetReached)

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
        for target in values:
            await asyncio.sleep(dt)
            self.set_trait('value', Q_(target, 'mm'))

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
        dataSet = DataSet(np.array(self.counter), [])
        self.counter += 1
        return dataSet


class DummyContinuousDataSource(DataSource):

    def __init__(self, manip):
        super().__init__()
        self.manip = manip

    async def readDataSet(self):
        taxis = np.arange(self.manip._start.magnitude,
                          self.manip._stop.magnitude,
                          self.manip._step.magnitude) * self.manip._step.units
        omega = 2 * np.pi * 5 * ureg.THz
        data = np.sin(omega * taxis)
        data += 5e-3 * (np.random.random(data.shape) - 0.5) * np.max(data)
        data = data * ureg.nA
        dataSet = DataSet(data, [taxis])
        return dataSet
