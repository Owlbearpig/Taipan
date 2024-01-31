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
from dummy import DummyManipulator, DummyContinuousDataSource, DummyLockIn
from pathlib import Path
from pint import Quantity
import thz_context  # important for unit conversion

"""
Example MultiDataSourceScan
"""


class AppRoot(ComponentBase):
    currentData = DataSetTrait().tag(name="Current2 measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Time"])
    dataSaverDS1 = Instance(DataSaver)
    dataSaverDS2 = Instance(DataSaver)

    manipulator = Instance(DummyManipulator)

    multiDataSourceScan = Instance(MultiDataSourceScan)

    def __init__(self, loop=None):
        super().__init__(objectName="Example scan application", loop=loop)
        self.dataSaverDS1 = DataSaver(objectName="Data Saver DS 1")
        self.dataSaverDS2 = DataSaver(objectName="Data Saver DS 2")

        self.manipulator = DummyManipulator()
        self.manipulator.objectName = "Dummy stage (Not really doing much : ) )"
        self.manipulator.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.scan_manip = DummyManipulator()
        self.scan_manip.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.multiDataSourceScan = MultiDataSourceScan()
        self.multiDataSourceScan.manipulator = self.scan_manip
        self.dummy_ds1 = DummyContinuousDataSource(objectName="DS1")
        self.dummy_ds2 = DummyContinuousDataSource(objectName="DS2")
        self.multiDataSourceScan.registerDataSource(self.dummy_ds1)
        self.multiDataSourceScan.registerDataSource(self.dummy_ds2)

        self.multiDataSourceScan.minimumValue = Q_(840, "ps")
        self.multiDataSourceScan.maximumValue = Q_(860, "ps")
        self.multiDataSourceScan.overscan = Q_(1, "ps")
        self.multiDataSourceScan.step = Q_(10, "ps")
        self.multiDataSourceScan.positioningVelocity = Q_(40, "ps/s")
        self.multiDataSourceScan.scanVelocity = Q_(1000, "ps/s")

        self.dataSaverDS1.registerManipulator(self.scan_manip, "Position")
        self.dataSaverDS2.registerManipulator(self.scan_manip, "Position")

        self.dataSaverDS1.fileNameTemplate = "DS1-{date}-{name}-{Position}"
        self.dataSaverDS1.set_trait("path", Path(r""))
        self.dataSaverDS2.fileNameTemplate = "DS2-{date}-{name}-{Position}"
        self.dataSaverDS2.set_trait("path", Path(r""))
        self.dummy_ds1.addDataSetReadyCallback(self.dataSaverDS1.process)
        self.dummy_ds2.addDataSetReadyCallback(self.dataSaverDS2.process)

        self.dummy_ds1.addDataSetReadyCallback(self.setCurrentData)
        self.dummy_ds2.addDataSetReadyCallback(self.setCurrentData)

        self.minimumValue = Q_(0, "mm")
        self.maximumValue = Q_(10, "mm")
        self.positioningVelocity = Q_(1, "mm/s")
        self.scanVelocity = Q_(0.5, "mm/s")
        self.step = Q_(0.2, "mm")

    async def __aenter__(self):
        await super().__aenter__()
        await self.multiDataSourceScan.__aenter__()
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.multiDataSourceScan.__aexit__(*args)
        await self.manipulator.__aexit__(*args)

    @action("Take new measurement")
    async def takeMeasurement(self):
        new_datasets = await self.multiDataSourceScan.readDataSet()

    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)
