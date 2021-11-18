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

from common import ComponentBase, DataSource, Manipulator, DataSet, Scan, action
import asyncio
import numpy as np
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait, Quantity
from traitlets import Integer, Instance
from asyncioext import ensure_weakly_binding_future
from dummy import DummyManipulator, DummySimpleDataSource, DummyContinuousDataSource

import time


class AppRoot(ComponentBase):

    someDataSet = DataSetTrait().tag(name="Current measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Sample number"])

    scan = Instance(Scan)

    def __init__(self, loop=None):
        super().__init__(objectName="Example application", loop=loop)

        self.scan = Scan()

        self.scan.manipulator = DummyManipulator()
        self.scan.dataSource = DummyContinuousDataSource(self.scan.manipulator)

        self.scan.minimumValue = Q_(0, 'mm')
        self.scan.maximumValue = Q_(10, 'mm')
        self.scan.positioningVelocity = Q_(1, 'mm/s')
        self.scan.scanVelocity = Q_(0.5, 'mm/s')
        self.scan.step = Q_(0.2, 'mm')


    @action("Take new measurement")
    async def takeMeasurement(self):
        dataSet = await self.scan.readDataSet()
        self.set_trait('someDataSet', dataSet)
