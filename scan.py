# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 11:18:53 2015

@author: pumphaus
"""

from common import DataSource, DataSet
import numpy as np

class Scan(DataSource):
    def __init__(self, manipulator = None, dataSource = None, dim = 0, \
                 minimumValue = 0, maximumValue = 0, step = 0):
        super().__init__()
        self.manipulator = manipulator
        self.dataSource = dataSource
        self.dim = dim
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue
        self.step = 0
        self.continuousScan = False
        self.retractAtEnd = False

    async def _doContinuousScan(self, axis):
        await self.manipulator.moveTo(self.minimumValue - self.step)
        self.dataSource.start()
        await self.manipulator.moveTo(self.maximumValue)
        self.dataSource.stop()

        dataSet = await self.dataSource.readDataSet()
        dataSet.axes = dataSet.axes.copy()
        dataSet.axes[0] = axis
        return dataSet

    async def _doSteppedScan(self, axis):
        accumulator = []
        self.dataSource.start()
        for position in axis:
            await self.manipulator.moveTo(position)
            accumulator.append(await self.dataSource.readDataSet())
        self.dataSource.stop()

        axes = accumulator[0].axes.copy()
        axes.insert(0, axis)
        data = np.array([ dset.data for dset in accumulator ])

        return DataSet(data, axes)

    async def readDataSet(self):
        self.dataSource.stop()
        self.manipulator.step = self.step

        axis = np.arange(self.minimumValue, self.maximumValue, self.step)

        dataSet = None

        if self.continuousScan:
            dataSet = await self._doContinuousScan(self, axis)
        else:
            dataSet = await self._doSteppedScan(self, axis)

        if self.retractAtEnd:
            await self.manipulator.moveTo(self.minimumValue)

        return dataSet

    def processAndAdvance(self):
        pass

    def setAxisOnDataSet(self):
        pass

    def accumulateCurrentDataPoint(self):
        pass

    def createDataSetForCurrentScan(self):
        pass
