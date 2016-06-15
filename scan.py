# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 11:18:53 2015

@author: Arno Rehn
"""

import asyncio
from common import Manipulator, DataSource, DataSet
import numpy as np
import warnings
from traitlets import Bool, Float, Instance


class Scan(DataSource):

    manipulator = Instance(Manipulator, allow_none=True)
    dataSource = Instance(DataSource, allow_none=True)

    minimumValue = Float(0).tag(help="The Scan's minimum value",
                                name="Minimum value")
    maximumValue = Float(0).tag(help="The Scan's maximum value",
                                name="Maximum value")
    step = Float(0).tag(help="The step width used for the Scan",
                        name="Step width")
    scanVelocity = Float(0).tag(help="The velocity of the Manipulator used "
                                     "during the scan",
                                name="Scan velocity")
    positioningVelocity = Float(0).tag(help="The velocity of the Manipulator "
                                            "during positioning movement (not "
                                            "during data acquisiton)",
                                       name="Positioning velocity")
    continuousScan = Bool(False)
    retractAtEnd = Bool(False)
    active = Bool(False, read_only=True)

    def __init__(self, manipulator=None, dataSource=None, minimumValue=0,
                 maximumValue=0, step=0, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)

        self.observe(self._setUnits, 'manipulator')

        self.manipulator = manipulator
        self.dataSource = dataSource
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue
        self.step = step
        self.currentAxis = None

    def _setUnits(self, change):
        manip = change['new']
        if manip is None:
            return

        self.traits()['minimumValue'].metadata['unit'] = manip.unit
        self.traits()['maximumValue'].metadata['unit'] = manip.unit
        self.traits()['step'].metadata['unit'] = manip.unit
        self.traits()['positioningVelocity'].metadata['unit'] = \
            (manip.unit or '') + '/s'
        self.traits()['scanVelocity'].metadata['unit'] = \
            (manip.unit or '') + '/s'

    async def _doContinuousScan(self, axis, step):
        await self.manipulator.beginScan(axis[0], axis[-1],
                                         self.positioningVelocity)
        self.dataSource.start()
        # move half a step over the final position to ensure a trigger
        await self.manipulator.moveTo(axis[-1] + step / 2.0,
                                      self.scanVelocity)
        self.dataSource.stop()

        dataSet = await self.dataSource.readDataSet()
        dataSet.checkConsistency()
        dataSet.axes = dataSet.axes.copy()
        dataSet.axes[0] = axis

        expectedLength = len(dataSet.axes[0])

        # Oops, somehow the received amount of data does not match our
        # expectation
        if dataSet.data.shape[0] != expectedLength:
            warnings.warn("Length of recorded data set does not match "
                          "expectation. Actual length: %d, expected "
                          "length: %d - trimming." %
                          (dataSet.data.shape[0], expectedLength))
            if (dataSet.data.shape[0] < expectedLength):
                dataSet.axes[0] = np.resize(dataSet.axes[0],
                                            dataSet.data.shape[0])
            else:
                dataSet.data = np.resize(
                    dataSet.data,
                    (expectedLength,) + dataSet.data.shape[1:]
                )

        return dataSet

    async def _doSteppedScan(self, axis):
        accumulator = []
        self.dataSource.start()
        for position in axis:
            await self.manipulator.moveTo(position, self.scanVelocity)
            accumulator.append(await self.dataSource.readDataSet())
        self.dataSource.stop()

        axes = accumulator[0].axes.copy()
        axes.insert(0, axis)
        data = np.array([dset.data for dset in accumulator])

        return DataSet(data, axes)

    async def readDataSet(self):
        if self.active:
            raise asyncio.InvalidStateError()

        self.set_trait('active', True)

        try:
            self.dataSource.stop()
            await self.manipulator.waitForTargetReached()

            # ensure correct step sign
            theStep = abs(self.step)
            if (self.maximumValue < self.minimumValue):
                theStep = -theStep

            realStep, realStart, realStop = \
                await self.manipulator.configureTrigger(theStep,
                                                        self.minimumValue,
                                                        self.maximumValue)

            axis = np.arange(realStart, realStop, realStep)
            self.currentAxis = np.copy(axis)

            dataSet = None

            if self.continuousScan:
                dataSet = await self._doContinuousScan(axis, realStep)
            else:
                dataSet = await self._doSteppedScan(axis)

            return dataSet

        finally:
            self.dataSource.stop()
            if self.retractAtEnd:
                self._loop.create_task(
                    self.manipulator.moveTo(realStart,
                                            self.positioningVelocity)
                )

            self.currentAxis = None
            self.set_trait('active', False)
