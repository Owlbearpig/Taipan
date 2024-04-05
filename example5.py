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

from common import ComponentBase, Scan, action, TabularMeasurements2M
from common.save import DataSaver
from common.units import Q_
from common.traits import DataSet as DataSetTrait
from dummy import DummyManipulator, DummyContinuousDataSource, DummyLockIn
from pathlib import Path
from traitlets import Instance, Int
from pint import Quantity
from common.units import ureg
import thz_context # important for unit conversion

"""
Example table measurement with two manipulators
"""


class AppRoot(TabularMeasurements2M):
    currentData = DataSetTrait(read_only=True).tag(
        name="Time domain",
        axes_labels=["Time"],
        data_label="Amplitude",
        is_power=False)

    dataSaver = Instance(DataSaver)

    nMeasurements = Int(1, min=1).tag(name="No. of measurements", priority=99)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName="PI tabular measurements",
                         loop=loop)

        self.dataSaver = DataSaver(objectName="Data Saver")

        pi_stage = DummyManipulator()
        pi_stage.objectName = "PI C-863 DLine"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)

        self.TimeDomainScan = Scan(objectName="TimeDomainScan")
        self.TimeDomainScan.manipulator = pi_stage
        self.TimeDomainScan.dataSource = DummyLockIn()
        self.TimeDomainScan.dataSource.objectName = "SR830 dummy"

        self.TimeDomainScan.continuousScan = True
        self.TimeDomainScan.minimumValue = Q_(1250, "ps")
        self.TimeDomainScan.maximumValue = Q_(1315, "ps")
        self.TimeDomainScan.overscan = Q_(3, "ps")
        self.TimeDomainScan.step = Q_(0.05, "ps")
        self.TimeDomainScan.positioningVelocity = Q_(30, "ps/s")
        self.TimeDomainScan.scanVelocity = Q_(1.6, "ps/s")
        self.TimeDomainScan.retractAtEnd = True

        self.dataSource = self.TimeDomainScan

        manipulator1 = DummyManipulator()
        manipulator1.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)  # added JanO 22.1.2019
        manipulator1.objectName = "PI C-863 1"
        self.manipulator1 = manipulator1
        self.positioningVelocityM1 = Q_(4, "mm/s")
        self.scanVelocity = Q_(4, "mm/s")
        self.manipulator1.set_limits(min_=Q_(-15, "mm"), max_=Q_(110, "mm"))

        manipulator2 = DummyManipulator()
        manipulator2.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)
        manipulator2.objectName = "PI C-863 2"
        self.positioningVelocityM2 = Q_(4, "mm/s")
        self.manipulator2 = manipulator2
        # self.manipulator2.set_limits(min_=Q_(-15, "mm"), max_=Q_(15, "mm"))

        self.dataSaver.registerManipulator(self.manipulator1, "Position1")
        self.dataSaver.registerManipulator(self.manipulator2, "Position2")
        self.dataSaver.registerObjectAttribute(self, "currentMeasurementName", "currentTableEntry")
        self.dataSaver.fileNameTemplate = "{date}-{name}-{currentTableEntry}-{Position1}-{Position2}"
        self.dataSaver.set_trait("path", Path(r""))
        self.TimeDomainScan.addDataSetReadyCallback(self.dataSaver.process)
        self.TimeDomainScan.addDataSetReadyCallback(self.setCurrentData)
        self._backAndForth = True

    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)

    async def __aenter__(self):
        await super().__aenter__()
        return self

    @action("Take Tabular measurements")
    async def takeTabularScan(self):
        self.set_trait("progress2", 0)  # progress trait changes added by Cornelius for additional progress Information
        for x in range(self.nMeasurements):
            dataset = await self.readDataSet()
            self.set_trait("progress2", (x + 1) / self.nMeasurements)

    @action("Take No. of measurements")
    async def takeSingleMeasurements(self):
        self.set_trait("progress", 0)  # progress trait changes added by Cornelius for additional progress Information
        self.set_trait("progress2", 0)
        for x in range(self.nMeasurements):
            dataset = await self.TimeDomainScan.readDataSet()
            self.set_trait("progress", (x + 1) / self.nMeasurements)
            self.set_trait("progress2", (x + 1) / self.nMeasurements)

    @action("Stop")
    async def stop(self):  # added by Cornelius to Stop both tabular scan and multiple measurements scan
        if not self._activeFuture:
            if not self.TimeDomainScan._activeFuture:
                return
            self.TimeDomainScan._activeFuture.cancel()
            return
        self._activeFuture.cancel()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
