# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 14:56:08 2015

@author: pumphaus
"""

from common import DataSource, Manipulator, DataSet
import numpy as np

class DummyManipulator(Manipulator):
    pass

class DummySimpleDataSource(DataSource):
    def __init__(self, init = 0):
        super().__init__()
        self.init = init
        self.stop()

    def stop(self):
        self.counter = self.init

    async def readDataSet(self):
        dataSet = DataSet(np.array(self.counter), [])
        self.counter += 1;
        return dataSet

class DummyContinuousDataSource(DataSource):
    def __init__(self, init, count):
        super().__init__()
        self.init = init
        self.count = count

    async def readDataSet(self):
        dataSet = DataSet(np.arange(self.init, self.init + self.count),
                          [ np.arange(0, self.count) ])
        return dataSet
