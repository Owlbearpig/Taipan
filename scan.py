# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 11:18:53 2015

@author: Arno Rehn
"""

import asyncio
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
        self.step = step
        self.continuousScan = False
        self.retractAtEnd = False

    async def _doContinuousScan(self, axis):
        await self.manipulator.beginScan(axis[0], axis[-1])
        self.dataSource.start()
        await self.manipulator.moveTo(axis[-1])
        self.dataSource.stop()

        dataSet = await self.dataSource.readDataSet()
        if dataSet.data.ndim != len(dataSet.axes):
            raise Exception("Axes/data mismatch. Data dimension: %d, number of"
                            " axes: %d" %
                            (dataSet.data.ndim, len(dataSet.axes)))

        dataSet.axes = dataSet.axes.copy()
        dataSet.axes[0] = axis

        expectedLength = len(dataSet.axes[0])

        # Oops, we have more data points than axis points...
        if dataSet.data.shape[0] != expectedLength:
            # If we're only off by one, then the maximumValue has probably
            # triggered another acquisition. Simply drop the last one.
            if dataSet.data.shape[0] == expectedLength + 1:
                dataSet.data = dataSet.data[:-1]
            else:
                raise Exception("Length of recorded data set does not match "
                                "expectation. Actual length: %d, expected "
                                "length: %d" %
                                (dataSet.data.shape[0], expectedLength))

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
        await self.manipulator.waitForTargetReached()

        realStep, realStart, realStop = \
            await self.manipulator.configureTrigger(self.step,
                                                    self.minimumValue,
                                                    self.maximumValue)

        axis = np.arange(realStart, realStop, realStep)

        dataSet = None

        if self.continuousScan:
            dataSet = await self._doContinuousScan(axis)
        else:
            dataSet = await self._doSteppedScan(axis)

        if self.retractAtEnd:
            asyncio.ensure_future(self.manipulator.moveTo(realStart))

        return dataSet

    def processAndAdvance(self):
        pass

    def setAxisOnDataSet(self):
        pass

    def accumulateCurrentDataPoint(self):
        pass

    def createDataSetForCurrentScan(self):
        pass
