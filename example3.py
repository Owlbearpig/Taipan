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
import time

from common import ComponentBase, Scan, action, DataSource
from common.save import DataSaver
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyContinuousDataSource
from pathlib import Path
from pint import Quantity
import thz_context # important for unit conversion

"""
Example scan, datasource + manip
"""


class AppRoot(Scan):

    someDataSet = DataSetTrait().tag(name="Current measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Sample number"])

    dataSaver = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Example application", loop=loop)
        self.dataSaver = DataSaver(objectName="Data Saver")

        self.manipulator = DummyManipulator()
        self.dataSource = DummyContinuousDataSource(self.manipulator)

        self.dataSaver.registerManipulator(self.manipulator, "Position")
        self.dataSaver.fileNameTemplate = "{date}-{name}-{Position}"
        self.dataSaver.set_trait("path", Path(r"E:\Projects\Python\taipan\measurements"))
        self.dataSource.addDataSetReadyCallback(self.dataSaver.process)
        self.dataSource.addDataSetReadyCallback(self.setCurrentData)

        self.minimumValue = Q_(0, "mm")
        self.maximumValue = Q_(10, "mm")
        self.positioningVelocity = Q_(1, "mm/s")
        self.scanVelocity = Q_(0.5, "mm/s")
        self.step = Q_(0.2, "mm")


    async def __aenter__(self):
        await self.dataSource.__aenter__()  # lockin
        return self


    async def __aexit__(self, *args):
        await self.dataSource.__aexit__(*args)  # lockin

        await super().__aexit__(*args)


    @action("Take new measurement")
    async def takeMeasurement(self):
        await self.readDataSet()

    def setCurrentData(self, dataSet):
        self.set_trait("someDataSet", dataSet)
