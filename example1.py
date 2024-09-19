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
from common.traits import Quantity
from traitlets import Instance, Float, Bool, Int
from dummy import DummyManipulator, DummyContinuousDataSource
from pathlib import Path
import enum
import traitlets

"""
Example take measurements using dummy source
Measurement parameters set on two dummy manipulators
"""




class AppRoot(ComponentBase):
    class CurveBufferTriggerOutput(enum.Enum):
        PerCurve = 0
        PerPoint = 1

    someDataSet = DataSetTrait().tag(name="Current measurement",
                                     data_label="Amplitude",
                                     axes_labels=["Time"])

    bufferTriggerOutput = traitlets.Enum(CurveBufferTriggerOutput, command="TRIGOUT", group="Data Curve Buffer")

    dataSaver = Instance(DataSaver)
    ds = Instance(DummyContinuousDataSource)

    nMeasurements = Int(1, min=1).tag(name="No. of measurements", priority=99)
    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")

    manip1 = Instance(DummyManipulator)
    #manip2 = Instance(DummyManipulator)

    def __init__(self, loop=None):
        super().__init__(objectName="Cont. source with manip", loop=loop)
        self.manip1 = DummyManipulator()
        #self.manip2 = DummyManipulator()
        self.ds = DummyContinuousDataSource()
        self.manip1.set_limits(min_=Q_(-15, "mm"), max_=Q_(15, "mm"))

        self.dataSaver = DataSaver(objectName="Data Saver")
        self.dataSaver.registerManipulator(self.manip1, "Position1")
        #self.dataSaver.registerManipulator(self.manip2, "Position2")
        #self.dataSaver.fileNameTemplate = "{date}-{name}-{Position1}-{Position2}"
        self.dataSaver.fileNameTemplate = "{date}-{name}-{Position1}"
        self.dataSaver.set_trait("path", Path(r""))
        self.ds.addDataSetReadyCallback(self.dataSaver.process)

        self.data_acq_task = None

    @action("Take new measurement")
    async def takeMeasurement(self):
        dataSet = await self.ds.readDataSet()
        self.set_trait("someDataSet", dataSet)

    @action("start acquisition")
    async def startAcquisition(self):
        self.data_acq_task = self._loop.create_task(self.ds.update_live_data())
        self.ds.set_trait("acq_on", True)

    @action("stop acquisition")
    async def stopAcquisition(self):
        if self.data_acq_task:
            self.data_acq_task.cancel()
            self.ds.set_trait("acq_on", False)

    @action("Take No. of measurements")
    async def takeSingleMeasurements(self):
        self.set_trait("progress", 0)
        for x in range(self.nMeasurements):
            dataSet = await self.ds.readDataSet()
            self.set_trait("progress", (x + 1) / self.nMeasurements)
            self.set_trait("someDataSet", dataSet)

    @action("do something")
    def do_this(self):
        targetValueTrait = self.manip1.class_traits()["targetValue"]
        print(bool(targetValueTrait.min))
