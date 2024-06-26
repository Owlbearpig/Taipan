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
from datasources.siradr4 import SiRadR4
from pathlib import Path
from dummy import DummyManipulator
import os

if os.name == "nt":
    comport = "COM5"
elif os.name == "posix":
    comport = "/dev/ttyUSB4"
else:
    comport = None


class AppRoot(ComponentBase):

    dataSaver = Instance(DataSaver)
    ds = Instance(SiRadR4)
    manip = Instance(DummyManipulator)

    nMeasurements = Int(1, min=1).tag(name="No. of measurements", priority=99)
    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")

    current_amp_data = DataSetTrait(read_only=True).tag(name="Live amplitude data",
                                                        data_label="Amplitude",
                                                        axes_labels=["Frequency"],
                                                        simple_plot=True)
    current_phi_data = DataSetTrait(read_only=True).tag(name="Live phase data",
                                                        data_label="Phase",
                                                        axes_labels=["Frequency"],
                                                        simple_plot=True)
    current_cfar_data = DataSetTrait(read_only=True).tag(name="Live CFAR data",
                                                         data_label="CFAR",
                                                         axes_labels=["Frequency"],
                                                         simple_plot=True,
                                                         visible=False)

    def __init__(self, loop=None):
        super().__init__(objectName="Test setup", loop=loop)
        self.ds = SiRadR4(objectName="Si-Radar R4", port=comport)
        self.manip = DummyManipulator()
        self.dataSaver = DataSaver(objectName="Data Saver")
        self.dataSaver.registerManipulator(self.manip, "Position")
        self.dataSaver.fileNameTemplate = "{date}-{name}-{dataType}-{Position}"
        self.dataSaver.set_trait("path", Path(r""))

        self.ds.addDataSetReadyCallback(self.dataSaver.process)

    @action("Take n measurements")
    async def take_n_measurements(self):
        self.set_trait("progress", 0)
        for x in range(self.nMeasurements):
            dataSets = await self.ds.readDataSet()
            for dataSet in dataSets:
                if dataSet.dataType == 'R':
                    self.set_trait("current_amp_data", dataSet)
                elif dataSet.dataType == 'P':
                    self.set_trait("current_phi_data", dataSet)
                elif dataSet.dataType == 'C':
                    self.set_trait("current_cfar_data", dataSet)
                elif dataSet.dataType == 'T':
                    pass
                else:
                    pass

            self.set_trait("progress", (x + 1) / self.nMeasurements)
