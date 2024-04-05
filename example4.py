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

from common import ComponentBase, Scan, action, DataSource
from common.save import DataSaver
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyContinuousDataSource, DummyLockIn
from pathlib import Path
from pint import Quantity
import thz_context  # important for unit conversion

"""
Example scan with datasource(data source + stage)
"""


class AppRoot(Scan):
    currentData = DataSetTrait().tag(name="Current measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Time"])

    dataSaver = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Example scan application", loop=loop)
        self.dataSaver = DataSaver(objectName="Data Saver")

        self.dummy_stage = DummyManipulator()
        self.dummy_stage.objectName = "Dummy stage"
        self.dummy_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.TimeDomainScan = Scan(objectName="TimeDomainScan")

        self.TimeDomainScan.manipulator = self.dummy_stage
        self.TimeDomainScan.dataSource = DummyLockIn()

        self.TimeDomainScan.dataSource.objectName = "SR7230 (Dummy)"

        self.TimeDomainScan.continuousScan = True
        self.TimeDomainScan.minimumValue = Q_(840, "ps")
        self.TimeDomainScan.maximumValue = Q_(910, "ps")
        self.TimeDomainScan.overscan = Q_(1, "ps")
        self.TimeDomainScan.step = Q_(0.05, "ps")
        self.TimeDomainScan.positioningVelocity = Q_(40, "ps/s")
        self.TimeDomainScan.scanVelocity = Q_(1, "ps/s")
        self.TimeDomainScan.retractAtEnd = True

        self.manipulator = DummyManipulator()
        self.dataSource = self.TimeDomainScan

        self.dataSaver.registerManipulator(self.manipulator, "Position")
        self.dataSaver.fileNameTemplate = "{date}-{name}-{Position}"
        self.dataSaver.set_trait("path", Path(r""))
        self.dataSource.addDataSetReadyCallback(self.dataSaver.process)
        self.dataSource.addDataSetReadyCallback(self.setCurrentData)

        self.minimumValue = Q_(0, "mm")
        self.maximumValue = Q_(10, "mm")
        self.positioningVelocity = Q_(1, "mm/s")
        self.scanVelocity = Q_(0.5, "mm/s")
        self.step = Q_(0.2, "mm")

    async def __aenter__(self):
        await super().__aenter__()
        await self.dataSource.__aenter__()  # lockin
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.dataSource.__aexit__(*args)  # lockin
        await self.manipulator.__aexit__(*args)
        await self.dummy_stage.__aexit__(*args)

    @action("Take new measurement")
    async def takeMeasurement(self):
        await self.readDataSet()

    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)
