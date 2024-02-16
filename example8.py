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

from common import ComponentBase, Scan, action, DataSource, MultiDataSource
from common.save import DataSaver
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyDoubleDatasource, DummyContinuousDataSource
from pathlib import Path
from pint import Quantity
import thz_context  # important for unit conversion

"""
Multidatasource example
"""


class AppRoot(Scan):
    dataSaverDS1 = Instance(DataSaver)
    dataSaverDS2 = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Example scan application", loop=loop)
        self.dataSaverDS1 = DataSaver(objectName="Data Saver DS1")
        self.dataSaverDS2 = DataSaver(objectName="Data Saver DS2")

        self.dummy_stage = DummyManipulator()
        self.dummy_stage.objectName = "Dummy stage"
        self.dummy_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.manipulator = DummyManipulator()

        self.cont_ds1 = DummyContinuousDataSource(freq=1.0)
        self.cont_ds2 = DummyContinuousDataSource(freq=2.0)

        self.multi_ds = MultiDataSource()
        self.multi_ds.register_datasource(self.cont_ds1)
        self.multi_ds.register_datasource(self.cont_ds2)
        self.dataSource = self.multi_ds

        self.dataSaverDS1.registerManipulator(self.manipulator, "Position")
        self.dataSaverDS1.fileNameTemplate = "{date}-{name}-{Position}"
        self.dataSaverDS1.set_trait("path", Path(r""))

        self.dataSaverDS2.registerManipulator(self.manipulator, "Position")
        self.dataSaverDS2.fileNameTemplate = "{date}-{name}-{Position}"
        self.dataSaverDS2.set_trait("path", Path(r""))

        self.cont_ds1.addDataSetReadyCallback(self.dataSaverDS1.process)
        self.cont_ds2.addDataSetReadyCallback(self.dataSaverDS2.process)

    async def __aenter__(self):
        await super().__aenter__()
        await self.multi_ds.__aenter__()
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.multi_ds.__aexit__(*args)


