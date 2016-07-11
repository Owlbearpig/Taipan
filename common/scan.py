# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 11:18:53 2015

@author: Arno Rehn
"""

import asyncio
from common import Manipulator, DataSource, DataSet, action
import numpy as np
import warnings
from traitlets import Bool, Float, Instance
from copy import deepcopy
from common.traits import Quantity
from common.units import Q_


class Scan(DataSource):

    manipulator = Instance(Manipulator, allow_none=True)
    dataSource = Instance(DataSource, allow_none=True)

    minimumValue = Quantity(Q_(0), help="The Scan's minimum value").tag(
                                   name="Minimum value",
                                   priority=0)

    maximumValue = Quantity(Q_(0), help="The Scan's maximum value").tag(
                                   name="Maximum value",
                                   priority=1)

    step = Quantity(Q_(0), help="The step width used for the Scan",
                           min=Q_(0)).tag(
                           name="Step width")

    scanVelocity = Quantity(Q_(0), help="The velocity of the Manipulator used "
                                        "during the scan").tag(
                                   name="Scan velocity")

    positioningVelocity = Quantity(Q_(0), help="The velocity of the "
                                               "Manipulator during positioning"
                                               " movement (not during data "
                                               "acquisiton)").tag(
                                          name="Positioning velocity")

    retractAtEnd = Bool(False, help="Retract the manipulator to the start "
                                    "position at the end of the scan.").tag(
                               name="Retract manipulator at end")

    active = Bool(False, read_only=True, help="Whether the scan is currently "
                                              "acquiring data").tag(
                                         name="Active")

    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")

    def __init__(self, manipulator=None, dataSource=None, minimumValue=Q_(0),
                 maximumValue=Q_(0), step=Q_(0), objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)

        self.observe(self._setUnits, 'manipulator')

        self.manipulator = manipulator
        self.dataSource = dataSource
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue
        self.step = step
        self.continuousScan = False
        self._activeFuture = None

        self.__original_class = self.__class__

    def _setUnits(self, change):
        """Copy the unit from the Manipulator to the metadata of the traits."""

        self.__class__ = self.__original_class

        manip = change['new']
        if manip is None:
            return

        traitsWithBaseUnits = ['minimumValue', 'maximumValue', 'step']
        traitsWithVelocityUnits = ['positioningVelocity', 'scanVelocity']

        baseUnits = manip.trait_metadata('value', 'preferred_units')
        velocityUnits = manip.trait_metadata('velocity', 'preferred_units')

        newTraits = {}

        for name, trait in self.traits().items():
            if name in traitsWithBaseUnits or name in traitsWithVelocityUnits:
                newTrait = deepcopy(trait)
                newTrait.metadata['preferred_units'] = baseUnits
                newTrait.default_value = 0 * baseUnits
                if newTrait.min is not None:
                    newTrait.min = 0 * baseUnits
                if name in traitsWithVelocityUnits:
                    newTrait.metadata['preferred_units'] = velocityUnits
                    newTrait.default_value = 0 * velocityUnits

                newTraits[name] = newTrait

        self.add_traits(**newTraits)

    def updateProgress(self, axis):
        delta = axis[-1] - axis[0]

        def updateProgress(change=None):
            if change:
                val = change['new']
            else:
                val = self.manipulator.value

            val = val.to(axis.units)
            val = val - axis[0]
            prog = float(val / delta)

            prog = max(0, min(1, prog))
            self.set_trait('progress', prog)

        return updateProgress

    async def _doContinuousScan(self, axis, step):
        await self.manipulator.beginScan(axis[0], axis[-1],
                                         self.positioningVelocity)

        updater = self.updateProgress(axis)
        try:
            self.manipulator.observe(updater, 'value')

            self.dataSource.start()
            # move half a step over the final position to ensure a trigger
            await self.manipulator.moveTo(axis[-1] + step / 2.0,
                                          self.scanVelocity)
            self.dataSource.stop()

        finally:
            self.manipulator.unobserve(updater, 'value')

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
        data = np.array([dset.data.magnitude for dset in accumulator])
        data = data * accumulator[0].units

        return DataSet(data, axes)

    @action("Stop")
    def stop(self):
        if not self._activeFuture:
            return

        self._activeFuture.cancel()

    def readDataSet(self):
        self._activeFuture = self._loop.create_task(self._readDataSetImpl())
        return self._activeFuture

    async def _readDataSetImpl(self):
        if not self._activeFuture:
            raise asyncio.InvalidStateError()

        if self.active:
            raise asyncio.InvalidStateError()

        self.set_trait('active', True)
        self.set_trait('progress', 0)

        try:
            self.dataSource.stop()
            await self.manipulator.waitForTargetReached()

            step = abs(self.step)
            stepUnits = step.units
            min = self.minimumValue.to(stepUnits)
            max = self.maximumValue.to(stepUnits)

            # ensure correct step sign
            if (max < min):
                step = -step

            realStep, realStart, realStop = \
                await self.manipulator.configureTrigger(step, min, max)

            realStep = realStep.to(stepUnits)
            realStart = realStart.to(stepUnits)
            realStop = realStop.to(stepUnits)

            axis = np.arange(realStart.magnitude,
                             realStop.magnitude,
                             realStep.magnitude) * stepUnits

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

            self.set_trait('active', False)
            self._activeFuture = None
