# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 14:56:08 2015

@author: pumphaus
"""

from common import DataSource, Manipulator, DataSet
import asyncio
import numpy as np


class DummyManipulator(Manipulator):

    def __init__(self):
        super().__init__()
        self._val = 0

    def _getValue(self):
        return self._val

    @property
    def status(self):
        return self.Status.TargetReached

    async def moveTo(self, val, velocity=None):
        self.velocity = velocity
        values = np.linspace(self._val, val, 50)
        dt = abs(np.mean(np.diff(values)) / velocity)
        for target in values:
            await asyncio.sleep(dt)
            self._val = target

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
        taxis = np.arange(self.manip._start,
                          self.manip._stop, self.manip._step)
        omega = 2 * np.pi * 5
        data = np.sin(omega * taxis)
        dataSet = DataSet(data, [taxis])
        return dataSet
