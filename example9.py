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

from common import ComponentBase, Scan, action, DataSource, MultiDataSourceScan
from common.save import DataSaver
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyComboDataSauce, DummyLockIn
from pathlib import Path
from pint import Quantity
import thz_context  # important for unit conversion

"""
Example MultiDataSourceScan
"""


class AppRoot(Scan):
    currentData = DataSetTrait().tag(name="Current2 measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Time"])
    dataSaver = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Example scan application", loop=loop)
        self.dataSaver = DataSaver(objectName="Data Saver")

        self.dummyStage = DummyManipulator()
        self.dummyStage.objectName = "Dummy stage"
        self.dummyStage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.scan_manip = DummyManipulator()
        self.multiDataSourceScan = MultiDataSourceScan()
        self.multiDataSourceScan.continuousScan = True
        self.multiDataSourceScan.minimumValue = Q_(840, "ps")
        self.multiDataSourceScan.maximumValue = Q_(910, "ps")
        self.multiDataSourceScan.overscan = Q_(1, "ps")
        self.multiDataSourceScan.step = Q_(0.05, "ps")
        self.multiDataSourceScan.positioningVelocity = Q_(40, "ps/s")
        self.multiDataSourceScan.scanVelocity = Q_(1, "ps/s")
        self.multiDataSourceScan.retractAtEnd = True
        self.multiDataSourceScan.manipulator = self.scan_manip
        self.multiDataSourceScan.dummy_lockin1 = DummyLockIn()
        self.dummy_lockin1 = DummyLockIn(objectName="lockin1")
        self.dummy_lockin2 = DummyLockIn(objectName="lockin2")
        self.multiDataSourceScan.registerDataSource(self.dummy_lockin1)
        self.multiDataSourceScan.registerDataSource(self.dummy_lockin2)

        self.dataSource = self.multiDataSourceScan

        self.multiDataSourceScan.dataSource2 = Instance(DummyLockIn)

        self.manipulator = self.dummyStage
        self.dataSaver.registerManipulator(self.manipulator, "Position")
        #self.dataSaver.registerDataSource(self.dummy_lockin1, "DataSource")
        #self.dataSaver.registerDataSource(self.dummy_lockin2, "DataSource")

        self.dataSaver.fileNameTemplate = "{date}-{name}-{Position}"
        self.dataSaver.set_trait("path", Path(r""))
        self.dataSource.addDataSetReadyCallback(self.dataSaver.process)
        # self.dataSource.addDataSetReadyCallback(self.setCurrentData)

        self.minimumValue = Q_(0, "mm")
        self.maximumValue = Q_(10, "mm")
        self.positioningVelocity = Q_(1, "mm/s")
        self.scanVelocity = Q_(0.5, "mm/s")
        self.step = Q_(0.2, "mm")

    async def __aenter__(self):
        await super().__aenter__()
        await self.dataSource.__aenter__()
        await self.dummy_lockin1.__aenter__()
        await self.dummy_lockin2.__aenter__()
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.dataSource.__aexit__(*args)  # lockin
        await self.manipulator.__aexit__(*args)
        await self.dummyStage.__aexit__(*args)

    @action("Take new measurement")
    async def takeMeasurement(self):
        new_datasets = await self.readDataSet()

        print(new_datasets.axes)

    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)
