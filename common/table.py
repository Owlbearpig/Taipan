# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2015 - 2017 Arno Rehn <arno@arnorehn.de>

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
from traitlets import Bool, Float, Instance, Unicode
from copy import deepcopy
from common.traits import Quantity, Path
from common.units import Q_
import csv


class TabularMeasurements(DataSource):

    manipulator = Instance(Manipulator, allow_none=True)
    dataSource = Instance(DataSource, allow_none=True)

    positioningVelocity = Quantity(Q_(1), help="The velocity of the "
                                               "Manipulator during positioning"
                                               " movement").tag(
                                          name="Positioning velocity",
                                          priority=4)

    active = Bool(False, read_only=True, help="Whether the tabular measurement"
                                              "is currently running").tag(
                                         name="Active")

    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")

    tableFile = Path(None, is_file=True, is_dir=False, must_exist=True, allow_none=True).tag(
                     name="Table file")

    currentMeasurementName = Unicode(read_only=True).tag(name="Current")


    def __init__(self, manipulator: Manipulator=None,
                 dataSource: DataSource=None, objectName: str=None,
                 loop: asyncio.BaseEventLoop=None):
        super().__init__(objectName=objectName, loop=loop)

        self.__original_class = self.__class__

        self.observe(self._setUnits, 'manipulator')

        self.manipulator = manipulator
        self.dataSource = dataSource

        self._activeFuture = None

    def _setUnits(self, change):
        """Copy the unit from the Manipulator to the metadata of the traits."""

        self.__class__ = self.__original_class

        manip = change['new']
        if manip is None:
            return

        traitsWithBaseUnits = []
        traitsWithVelocityUnits = ['positioningVelocity']

        baseUnits = manip.trait_metadata('value', 'preferred_units')
        velocityUnits = manip.trait_metadata('velocity', 'preferred_units')

        newTraits = {}

        for name, trait in self.traits().items():
            if name in traitsWithBaseUnits or name in traitsWithVelocityUnits:
                newTrait = deepcopy(trait)
                newTrait.metadata['preferred_units'] = baseUnits
                newTrait.default_value = 0 * baseUnits
                if newTrait.min is not None:
                    newTrait.min = 1 * baseUnits
                if name in traitsWithVelocityUnits:
                    newTrait.metadata['preferred_units'] = velocityUnits
                    newTrait.default_value = 1 * velocityUnits

                newTraits[name] = newTrait

        self.add_traits(**newTraits)

    async def _doSteppedScan(self, names, axis):
        accumulator = []
        await self.dataSource.start()

        for i, (name, position) in enumerate(zip(names, axis)):
            self.set_trait('currentMeasurementName', name)
            await self.manipulator.moveTo(position, self.positioningVelocity)
            accumulator.append(await self.dataSource.readDataSet())
            self.set_trait('progress', (i + 1) / len(axis))

        self.set_trait('currentMeasurementName', '')

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

    def readDataSet(self):
        self._activeFuture = self._loop.create_task(self._readDataSetImpl())
        return self._activeFuture

    async def _readDataSetImpl(self):
        if not self._activeFuture:
            raise asyncio.InvalidStateError()

        if self.active:
            raise asyncio.InvalidStateError()

        if self.tableFile is None:
            raise RuntimeError("No table file specified!")

        names = []
        axis = []

        units = self.manipulator.trait_metadata('value', 'preferred_units')

        with self.tableFile.open() as table:
            reader = csv.reader(
                # Skip comments
                (row for row in table if not row.startswith('#')),
                dialect='unix', skipinitialspace=True)
            for row in reader:
                if len(row) != 2:
                    raise RuntimeError("Row has wrong amount of elements: '{}'"
                                       .format(row))

                names.append(row[0])

                try:
                    axis.append(Q_(float(row[1]), units))
                except ValueError:
                    raise RuntimeError("Failed to convert {} to a float!"
                                       .format(row[1]))

        self.set_trait('active', True)
        self.set_trait('progress', 0)

        try:
            await self.dataSource.stop()
            await self.manipulator.waitForTargetReached()

            dataSet = await self._doSteppedScan(names, axis)

            self._dataSetReady(dataSet)
            return dataSet

        finally:
            self._loop.create_task(self.dataSource.stop())
            self.manipulator.stop()
            self.set_trait('active', False)
            self._activeFuture = None
