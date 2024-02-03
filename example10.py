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

from common import ComponentBase, Scan, action, DataSource, MultiDataSourceScan, DataSet
from common.save import DataSaver
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyContinuousDataSource, DummyLockIn
from pathlib import Path
from pint import Quantity
import thz_context  # important for unit conversion

"""
Example MultiDataSourceScan
"""


class AppRoot(MultiDataSourceScan):
    dataSaverDS1 = Instance(DataSaver)
    dataSaverDS2 = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Example scan application", loop=loop)
        self.dataSaverDS1 = DataSaver(objectName="Data Saver DS 1")
        self.dataSaverDS2 = DataSaver(objectName="Data Saver DS 2")

        self.manip = DummyManipulator()
        self.manip.objectName = "Delay line"
        self.manip.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.manipulator = self.manip

        self.dummy_ds1 = DummyContinuousDataSource(objectName="DS1", freq=1)
        self.dummy_ds2 = DummyContinuousDataSource(objectName="DS2", freq=2)
        self.registerDataSource(self.dummy_ds1)
        self.registerDataSource(self.dummy_ds2)

        self.minimumValue = Q_(840, "ps")
        self.maximumValue = Q_(860, "ps")
        self.overscan = Q_(1, "ps")
        self.step = Q_(10, "ps")
        self.positioningVelocity = Q_(40, "ps/s")
        self.scanVelocity = Q_(1000, "ps/s")

        self.dataSaverDS1.registerManipulator(self.manipulator, "Position")
        self.dataSaverDS2.registerManipulator(self.manipulator, "Position")

        self.dataSaverDS1.fileNameTemplate = "DS1-{date}-{name}-{Position}"
        self.dataSaverDS1.set_trait("path", Path(r""))
        self.dataSaverDS2.fileNameTemplate = "DS2-{date}-{name}-{Position}"
        self.dataSaverDS2.set_trait("path", Path(r""))
        #self.dummy_ds1.addDataSetReadyCallback(self.dataSaverDS1.process)
        #self.dummy_ds2.addDataSetReadyCallback(self.dataSaverDS2.process)

        self.dummy_ds1.addDataSetReadyCallback(self.setCurrentDataDS1)
        self.dummy_ds2.addDataSetReadyCallback(self.setCurrentDataDS2)

    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.manipulator.__aexit__(*args)

    @action("Take new measurement")
    async def takeMeasurement(self):
        new_datasets = await self.readDataSet()

    @action("Take single measurement")
    async def takeSingleMeasurement(self):
        ds1 = await self.dummy_ds1.readDataSet()
        ds1.dataSource = self.dummy_ds1
        ds2 = await self.dummy_ds2.readDataSet()
        ds2.dataSource = self.dummy_ds2
        self.set_trait("currentData", ds1)
        self.set_trait("currentData", ds2)

    # could also add dataSet.dataSource = self to _dataSetReady, before callbacks are called
    # but then it would affect all datasources
    def setCurrentDataDS1(self, dataSet: DataSet):
        dataSet.dataSource = self.dummy_ds1
        self.set_trait("currentData", dataSet)

    def setCurrentDataDS2(self, dataSet: DataSet):
        dataSet.dataSource = self.dummy_ds2
        self.set_trait("currentData", dataSet)
