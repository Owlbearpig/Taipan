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
from common.traits import DataSet as DataSetTrait
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
        accumulator_dict = {}
        await self.dataSource.start()
        updater = self.updateProgress(axis)
        self.manipulator.observe(updater, 'value')
        for position in axis:
            await self.manipulator.moveTo(position, self.scanVelocity)
            if self.dataSource.is_multi_dataset_source:
                dataSets = await self.dataSource.readDataSet()
            else:
                dataSets = [await self.dataSource.readDataSet()]

            for dataSet in dataSets:
                if dataSet.dataType in accumulator_dict:
                    accumulator_dict[dataSet.dataType].append(dataSet)
                else:
                    accumulator_dict[dataSet.dataType] = [dataSet]

        self.manipulator.unobserve(updater, 'value')
        await self.dataSource.stop()

        accumulated_datasets = []
        for key in accumulator_dict.keys():
            accumulator = accumulator_dict[key]
            axes = accumulator[0].axes.copy()
            axes.insert(0, axis)
            data = np.array([dset.data.magnitude for dset in accumulator])
            data = data * accumulator[0].data.units
            accumulated_datasets.append(DataSet(data, axes))

        if self.dataSource.is_multi_dataset_source:
            return accumulated_datasets
        else:
            return accumulated_datasets[0]

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


class MultiDataSourceScan(Scan):
    currentData = DataSetTrait().tag(name="Live data",
                                     data_label="Amplitude",
                                     axes_labels=["Time"],
                                     is_multisource_plot=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dataSources = [self.dataSource]

    async def __aenter__(self):
        await super().__aenter__()
        for dSource in self._dataSources:
            await dSource.__aenter__()

    @staticmethod
    def add_attribute(attribute_name, attribute_value):
        def decorator(func):
            async def wrapper(*args, **kwargs):
                result = await func(*args, **kwargs)
                setattr(result, attribute_name, attribute_value)
                return result

            return wrapper

        return decorator

    def registerDataSource(self, dataSource: DataSource = None):

        if DataSource is None:
            return

        dataSource.readDataSet = self.add_attribute("dataSource_inst", dataSource)(dataSource.readDataSet)

        if self._dataSources[0] is None:
            self._dataSources[0] = dataSource
            self.dataSource = dataSource
            # return
        else:
            new_component_trait_name = f"dataSource{len(self._dataSources)}"
            self.add_traits(**{new_component_trait_name: Instance(DataSource)})
            self.setAttribute(new_component_trait_name, dataSource)
            self._dataSources.append(dataSource)

        if not self._dataSources[-1].objectName:
            self._dataSources[-1].objectName = f"DS{len(self._dataSources)}"

        MultiDataSourceScan.currentData.registered_dataSources.append(dataSource)

    async def _doSteppedScan(self, axis):
        accumulator = {}
        for dSource in self._dataSources:
            accumulator[dSource] = []
            await dSource.start()
        updater = self.updateProgress(axis)
        self.manipulator.observe(updater, 'value')
        for position in axis:
            await self.manipulator.moveTo(position, self.scanVelocity)
            for dSource in self._dataSources:
                accumulator[dSource].append(await dSource.readDataSet())
        self.manipulator.unobserve(updater, 'value')
        for dSource in self._dataSources:
            await dSource.stop()

        datasets = []
        for dSource in self._dataSources:
            first_dataset = accumulator[dSource][0]
            axes_dset = first_dataset.axes.copy()
            axes_dset.insert(0, axis)
            data = np.array([dSet.data.magnitude for dSet in accumulator[dSource]]) * first_dataset.data.units
            datasets.append(DataSet(data, axes_dset, dSource))

        return datasets

    async def _doContinuousScan(self, axis):
        overscan = self._getOverscan(axis)

        await self.manipulator.moveTo(axis[0] - overscan,
                                      self.positioningVelocity)

        prefUnits = axis.units
        axis = (await self.manipulator.configureTrigger(axis)).to(prefUnits)

        updater = self.updateProgress(axis)

        try:
            self.manipulator.observe(updater, 'value')

            for dSource in self._dataSources:
                try:
                    await dSource.start(scanAxis=axis)
                except TypeError:
                    await dSource.start()

            await self.manipulator.moveTo(axis[-1] + overscan,
                                          self.scanVelocity)
            for dSource in self._dataSources:
                await dSource.stop()

        finally:
            self.manipulator.unobserve(updater, 'value')

        dataSets = []
        for dSource in self._dataSources:
            dataSet = await dSource.readDataSet()
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

            dataSets.append(dataSet)

        return dataSets, axis

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
            for dSource in self._dataSources:
                await dSource.stop()
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

            if self.continuousScan:
                dSets, axis = await self._doContinuousScan(axis)
            else:
                dSets = await self._doSteppedScan(axis)

            for dSet in dSets:
                self._dataSetReady(dSet)

            return dSets

        except asyncio.CancelledError:
            logging.warning('Scan "{}" was cancelled'.format(self.objectName))
            raise

        finally:
            for dSource in self._dataSources:
                self._loop.create_task(dSource.stop())
            self.manipulator.stop()
            if self.retractAtEnd and axis is not None:
                self._loop.create_task(
                    self.manipulator.moveTo(axis[0] - self._getOverscan(axis),
                                            self.positioningVelocity)
                )

            self.set_trait('active', False)
            self._activeFuture = None
