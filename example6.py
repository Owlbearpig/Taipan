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

from common import ComponentBase, Scan, action
from common.save import DataSaver
from common.units import Q_
from common.traits import DataSet as DataSetTrait
from dummy import DummyManipulator, DummyContinuousDataSource, DummyLockIn
from pathlib import Path
from traitlets import Instance, Int
from pint import Quantity
from common.units import ureg
import thz_context  # important for unit conversion

"""
Example 2D scan with datasource(lockin + delay line) + two nested scans
"""


class AppRoot(Scan):
    currentData = DataSetTrait(read_only=True).tag(
        name="Time domain",
        axes_labels=["Time"],
        data_label="Amplitude",
        is_power=False)

    dataSaver = Instance(DataSaver)

    def __init__(self, loop=None):
        super().__init__(objectName="Y scan (manip 2)", loop=loop)

        self.delay_line = DummyManipulator()
        self.delay_line.objectName = "Delay line"
        self.delay_line.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.TimeDomainScan = Scan(objectName="TimeDomainScan")
        self.TimeDomainScan.manipulator = self.delay_line
        self.TimeDomainScan.dataSource = DummyLockIn()
        self.TimeDomainScan.dataSource.objectName = "Dummy Lockin"

        self.TimeDomainScan.continuousScan = True
        self.TimeDomainScan.minimumValue = Q_(0, "ps")
        self.TimeDomainScan.maximumValue = Q_(5, "ps")
        self.TimeDomainScan.overscan = Q_(1, "ps")
        self.TimeDomainScan.step = Q_(0.1, "ps")
        self.TimeDomainScan.positioningVelocity = Q_(30, "ps/s")
        self.TimeDomainScan.scanVelocity = Q_(1.6, "ps/s")
        self.TimeDomainScan.retractAtEnd = True

        self.manipx = DummyManipulator()
        self.manipy = DummyManipulator()

        self.XScan = Scan(objectName="X scan (manip 1)")
        self.XScan.manipulator = self.manipx
        self.XScan.dataSource = self.TimeDomainScan
        self.XScan.minimumValue = Q_(0, "mm")
        self.XScan.maximumValue = Q_(10, "mm")
        self.XScan.positioningVelocity = Q_(1, "mm/s")
        self.XScan.scanVelocity = Q_(0.5, "mm/s")
        self.XScan.step = Q_(0.2, "mm")
        self.XScan.retractAtEnd = True
        self.dataSource = self.XScan
        self._oldScanXStart = self.dataSource.start
        self._oldScanXStop = self.dataSource.stop
        self.dataSource.start = self.startScan
        self.dataSource.stop = self.stopScan

        self.manipulator = self.manipy
        self.YScan = Scan()
        self.YScan.manipulator = self.manipy
        self.YScan.dataSource = self.XScan
        self.YScan.minimumValue = Q_(0, "mm")
        self.YScan.maximumValue = Q_(10, "mm")
        self.YScan.positioningVelocity = Q_(1, "mm/s")
        self.YScan.scanVelocity = Q_(0.5, "mm/s")
        self.YScan.step = Q_(0.2, "mm")

        self.manipulator = self.manipy

        self.retractAtEnd = True
        self.minimumValue = Q_(0, 'mm')
        self.maximumValue = Q_(10, 'mm')
        self.step = Q_(2.5, 'mm')
        self.positioningVelocity = Q_(100, 'mm/s')
        self.scanVelocity = Q_(10, 'mm/s')

        # register the manipulators in the dataSaver
        self.dataSaver = DataSaver(objectName="Data Saver")
        self.dataSaver.registerManipulator(self.manipx, 'X')
        self.dataSaver.registerManipulator(self.manipy, 'Y')
        self.dataSaver.fileNameTemplate = '{date}-{name}-{X}-{Y}'
        self.TimeDomainScan.addDataSetReadyCallback(self.dataSaver.process)
        self.TimeDomainScan.addDataSetReadyCallback(self.setCurrentData)

    async def __aenter__(self):
        await super().__aenter__()
        await self.dataSource.__aenter__()  # lockin
        return self

    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)

    @action("Take new measurement")
    async def takeMeasurement(self):
        await self.readDataSet()

    async def startScan(self):
        await self._oldScanXStart()

    async def stopScan(self):
        await self._oldScanXStop()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.dataSource.__aexit__(*args)  # lockin
        await self.delay_line.__aexit__(*args)
        await self.manipx.__aexit__(*args)
        #await self.manipy.__aexit__(*args)
