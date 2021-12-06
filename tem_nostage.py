# -*- coding: utf-8 -*-
"""
Created on Tue Jul 26 15:05:52 2016

@author: Arno Rehn
"""

import asyncio
import traitlets
from traitlets import Instance
from common import ComponentBase, action
from common.save import DataSaver
from common.traits import DataSet as DataSetTrait
from datasources.tem_fiberstretcher import TEMFiberStretcher
import os

if os.name == 'unix':
    tem_port1 = '/dev/serial/by-id/usb-TEM_USB__-__Serial_cable-if00-port0'  # '/dev/ttyUSB1'
    tem_port2 = '/dev/serial/by-id/usb-TEM_USB__-__Serial_cable-if01-port0'  # '/dev/ttyUSB1'
else:
    tem_port1 = 'COM5'
    tem_port2 = 'COM6'


class AppRoot(ComponentBase):

    dataSaver = Instance(DataSaver)
    tem_fs = Instance(TEMFiberStretcher)
    currentMeasurement = DataSetTrait().tag(name="Current measurement",
                                            data_label="Amplitude",
                                            axes_labels=["Time"])

    progress = traitlets.Float(0, min=0, max=1, read_only=True).tag(name="Progress")
    nMeasurements = traitlets.Int(1, min=1).tag(name="No. of measurements", priority=99)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName="Measurement", loop=loop)
        self.title = "Taipan - Schweißgüte 2"

        self.dataSaver = DataSaver(objectName="Data Saver")
        self.tem_fs = TEMFiberStretcher(tem_port1, tem_port2, objectName="TEM FiberStretcher", loop=loop)

    @action("Take measurements")
    async def takeMeasurements(self):
        for i in range(self.nMeasurements):
            self.set_trait("currentMeasurement", await self.tem_fs.readDataSet())
            self.dataSaver.process(self.currentMeasurement)
            self.set_trait('progress', (i+1) / self.nMeasurements)
