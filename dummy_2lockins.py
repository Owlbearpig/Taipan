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

from common import ComponentBase, Scan, action, DataSource, MultiDataSourceScan
from common.save import DataSaver
from common.units import Q_, ureg
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyContinuousDataSource, DummyLockIn
from pathlib import Path
from pint import Quantity
import thz_context  # important for unit conversion

"""
Example MultiDataSourceScan
"""


class AppRoot(MultiDataSourceScan):

    dataSaver = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Example scan application", loop=loop)
        self.dataSaver = DataSaver(objectName="Data Saver")

        manipulator = DummyManipulator()
        manipulator.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        manipulator.objectName = "PI C-863"
        self.manipulator = manipulator

        self.lockin1 = DummyLockIn(objectName="DS1")
        self.lockin2 = DummyLockIn(objectName="DS2")

        self.manipulator.connect_trigger(self.lockin1)
        self.manipulator.connect_trigger(self.lockin2)

        self.registerDataSource(self.lockin1)
        self.registerDataSource(self.lockin2)

        self.continuousScan = True
        self.minimumValue = Q_(0, "ps")
        self.maximumValue = Q_(30, "ps")
        self.overscan = Q_(1, "ps")
        self.step = Q_(10, "ps")
        self.positioningVelocity = Q_(40, "ps/s")
        self.scanVelocity = Q_(10, "ps/s")
        self.retractAtEnd = True

        # self.dataSaver.registerManipulator(self.scan_manip, "Position")

        self.dataSaver.fileNameTemplate = "{date}-{name}-{dataSource}"
        self.dataSaver.set_trait("path", Path(r""))

        self.addDataSetReadyCallback(self.dataSaver.process)

        self.addDataSetReadyCallback(self.setCurrentData)

    @action("Take measurement")
    async def takeMeasurements(self):
        await self.readDataSet()

    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)

    async def __aenter__(self):
        await super().__aenter__()

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
