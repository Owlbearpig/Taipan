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

import asyncio
from common import Manipulator, DataSource, DataSet, action
import numpy as np
import warnings
from traitlets import Bool, Float, Instance
from copy import deepcopy
from common.traits import Quantity
from common.units import Q_
import logging


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
        name="Step width", priority=2)

    overscan = Quantity(Q_(0), help="The offset from the boundary positions",
                        min=Q_(0)).tag(name="Overscan", priority=3)

    scanVelocity = Quantity(Q_(0), help="The velocity of the Manipulator used "
                                        "during the scan").tag(
        name="Scan velocity", priority=4)

    positioningVelocity = Quantity(Q_(0), help="The velocity of the "
                                               "Manipulator during positioning"
                                               " movement (not during data "
                                               "acquisiton)").tag(
        name="Positioning velocity",
        priority=5)

    retractAtEnd = Bool(False, help="Retract the manipulator to the start "
                                    "position at the end of the scan.").tag(
        name="Retract manipulator at end")

    active = Bool(False, read_only=True, help="Whether the scan is currently "
                                              "acquiring data").tag(
        name="Active")

    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")

    def __init__(self, manipulator: Manipulator = None,
                 dataSource: DataSource = None, minimumValue=None,
                 maximumValue=None, step=None, objectName: str = None,
                 loop: asyncio.BaseEventLoop = None):
        super().__init__(objectName=objectName, loop=loop)

        self.__original_class = self.__class__

        self.observe(self._setUnits, 'manipulator')

        self.manipulator = manipulator
        self.dataSource = dataSource

        if minimumValue is not None:
            self.minimumValue = minimumValue

        if maximumValue is not None:
            self.maximumValue = maximumValue

        if step is not None:
            self.step = step

        self.continuousScan = False
        self._activeFuture = None

    def _setUnits(self, change):
        """Copy the unit from the Manipulator to the metadata of the traits."""

        self.__class__ = self.__original_class

        manip = change['new']
        if manip is None:
            return

        traitsWithBaseUnits = ['minimumValue', 'maximumValue', 'step',
                               'overscan']
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

    async def _confTriggerAndRealAxis(self, min, max, step):
        preferredUnits = step.units

        realStep, realStart, realStop = \
            await self.manipulator.configureTrigger(step, min, max)

        axis = np.arange(realStart.magnitude,
                         realStop.magnitude,
                         realStep.magnitude) * realStep.units

        axis = axis.to(preferredUnits)

        return axis

    def _getOverscan(self, axis):
        overscan = self.overscan

        # ensure correct overscan sign
        if axis[1].magnitude - axis[0].magnitude < 0:
            overscan = -overscan

        return overscan

    async def _doContinuousScan(self, axis):
        overscan = self._getOverscan(axis)

        await self.manipulator.moveTo(axis[0] - overscan,
                                      self.positioningVelocity)

        prefUnits = axis.units
        axis = (await self.manipulator.configureTrigger(axis)).to(prefUnits)

        updater = self.updateProgress(axis)

        try:
            self.manipulator.observe(updater, 'value')

            try:
                await self.dataSource.start(scanAxis=axis)
            except TypeError:
                await self.dataSource.start()

            await self.manipulator.moveTo(axis[-1] + overscan,
                                          self.scanVelocity)
            await self.dataSource.stop()

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
                dataSet.axes[0].resize(dataSet.data.shape[0])
            else:
                dataSet.data = dataSet.data.copy()
                dataSet.data.resize((expectedLength,) + dataSet.data.shape[1:])

        return dataSet, axis

    async def _doSteppedScan(self, axis):
        accumulator = []
        await self.dataSource.start()
        updater = self.updateProgress(axis)
        self.manipulator.observe(updater, 'value')
        for position in axis:
            await self.manipulator.moveTo(position, self.scanVelocity)
            accumulator.append(await self.dataSource.readDataSet())
        self.manipulator.unobserve(updater, 'value')
        await self.dataSource.stop()

        axes = accumulator[0].axes.copy()
        axes.insert(0, axis)
        data = np.array([dset.data.magnitude for dset in accumulator])
        data = data * accumulator[0].data.units

        return DataSet(data, axes)

    @action("Stop")
    async def stop(self):
        if not self._activeFuture:
            return

        self._activeFuture.cancel()

    def _createManipulatorIdleFuture(self):
        fut = self._loop.create_future()

        if self.manipulator.status == Manipulator.Status.Idle:
            fut.set_result(None)
            return fut

        def statusObserver(change):
            if change['new'] == Manipulator.Status.Idle:
                fut.set_result(None)

        self.manipulator.observe(statusObserver, 'status')

        fut.add_done_callback(lambda fut:
                              self.manipulator.unobserve(statusObserver, 'status'))

        return fut

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

        axis = None

        try:
            await self.dataSource.stop()
            await self._createManipulatorIdleFuture()

            step = abs(self.step)
            stepUnits = step.units
            min = self.minimumValue.to(stepUnits)
            max = self.maximumValue.to(stepUnits)

            # ensure correct step sign
            if (max < min):
                step = -step

            axis = (np.arange(min.magnitude, max.magnitude, step.magnitude)
                    * stepUnits)

            dataSet = None

            if self.continuousScan:
                dataSet, axis = await self._doContinuousScan(axis)
            else:
                dataSet = await self._doSteppedScan(axis)

            self._dataSetReady(dataSet)
            return dataSet

        except asyncio.CancelledError:
            logging.warning('Scan "{}" was cancelled'.format(self.objectName))
            raise

        finally:
            self._loop.create_task(self.dataSource.stop())
            self.manipulator.stop()
            if self.retractAtEnd and axis is not None:
                self._loop.create_task(
                    self.manipulator.moveTo(axis[0] - self._getOverscan(axis),
                                            self.positioningVelocity)
                )

            self.set_trait('active', False)
            self._activeFuture = None


class Scan2ds(Scan):
    dataSource2 = Instance(DataSource, allow_none=True)

    def __init__(self, datasource2: DataSource = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dataSource2 = datasource2

    async def _doSteppedScan(self, axis):
        accumulator = []
        await self.dataSource.start()
        await self.dataSource2.start()
        updater = self.updateProgress(axis)
        self.manipulator.observe(updater, 'value')
        for position in axis:
            await self.manipulator.moveTo(position, self.scanVelocity)
            accumulator.append((await self.dataSource.readDataSet(), await self.dataSource2.readDataSet()))
        self.manipulator.unobserve(updater, 'value')
        await self.dataSource.stop()
        await self.dataSource2.stop()

        first_dataset_ds1 = accumulator[0][0]
        first_dataset_ds2 = accumulator[0][1]

        axes = first_dataset_ds1.axes.copy()  # assuming axes are the same for both datasources
        axes.insert(0, axis)

        data_datasource1 = np.array([tup[0].data.magnitude for tup in accumulator]) * first_dataset_ds1.data.units
        data_datasource2 = np.array([tup[1].data.magnitude for tup in accumulator]) * first_dataset_ds2.data.units

        dataset1, dataset2 = DataSet(data_datasource1, axes), DataSet(data_datasource2, axes)

        return dataset1, dataset2

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

        axis = None

        try:
            await self.dataSource.stop()
            await self.dataSource2.stop()
            await self._createManipulatorIdleFuture()

            step = abs(self.step)
            stepUnits = step.units
            min = self.minimumValue.to(stepUnits)
            max = self.maximumValue.to(stepUnits)

            # ensure correct step sign
            if (max < min):
                step = -step

            axis = (np.arange(min.magnitude, max.magnitude, step.magnitude)
                    * stepUnits)

            dataSet1, dataSet2 = None, None

            if self.continuousScan:
                dataSet, axis = await self._doContinuousScan(axis)
            else:
                dataSet1, dataSet2 = await self._doSteppedScan(axis)

            self._dataSetReady(dataSet1)
            self._dataSetReady(dataSet2)
            return dataSet1, dataSet2

        except asyncio.CancelledError:
            logging.warning('Scan "{}" was cancelled'.format(self.objectName))
            raise

        finally:
            self._loop.create_task(self.dataSource.stop())
            self.manipulator.stop()
            if self.retractAtEnd and axis is not None:
                self._loop.create_task(
                    self.manipulator.moveTo(axis[0] - self._getOverscan(axis),
                                            self.positioningVelocity)
                )

            self.set_trait('active', False)
            self._activeFuture = None
