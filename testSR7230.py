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
import thz_context
from common.units import Q_, ureg
from common.traits import DataSet as DataSetTrait, Quantity
from traitlets import Integer, Instance
from asyncioext import ensure_weakly_binding_future
from datasources.sr7230 import SR7230
from dummy import DummyManipulator, DummySimpleDataSource
import pyvisa as visa
import os

import time

if os.name == 'posix':
    rm = visa.ResourceManager('@py')
elif os.name == 'nt':
    rm = visa.ResourceManager()

SR7230_USB_Port = 'USB0::0x0A2D::0x0027::14043751::RAW'
SR7230_LAN_Port = "TCPIP::169.254.150.230::50000::SOCKET"


class AppRoot(ComponentBase):

    someDataSet = DataSetTrait().tag(name="Current measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Sample number"])

    scan = Instance(Scan)

    def __init__(self, loop=None):
        super().__init__(objectName="Example application", loop=loop)

        self.scan = Scan()

        self.scan.manipulator = DummyManipulator()
        self.scan.dataSource = SR7230(rm.open_resource(SR7230_LAN_Port), ethernet=True)
        # self.scan.dataSource = SR7230(rm.open_resource(SR7230_USB_Port), ethernet=False)

        self.scan.continuousScan = True
        self.scan.minimumValue = Q_(0, 'mm')
        self.scan.maximumValue = Q_(10, 'mm')
        self.scan.positioningVelocity = Q_(1, 'mm/s')
        self.scan.scanVelocity = Q_(0.5, 'mm/s')
        self.scan.step = Q_(0.2, 'mm')

    async def __aenter__(self):
        # await super().__aenter__()
        await self.scan.dataSource.__aenter__()  # lockin

        return self

    async def __aexit__(self, *args):
        await self.scan.dataSource.__aexit__(*args)  # lockin
        await super().__aexit__(*args)

    @action("Take new measurement")
    async def takeMeasurement(self):
        dataSet = await self.scan.readDataSet()
        self.set_trait('someDataSet', dataSet)
