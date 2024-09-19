# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, traits, Scan, ureg, Q_, action, MultiDataSourceScan
from common.save import DataSaver
from traitlets import Instance, Float, Bool, Int
from pathlib import Path
from stages import PI
from datasources import SR830
import visa
import thz_context
import os

if os.name == 'posix':
    rm = visa.ResourceManager('@py')
elif os.name == 'nt':  # JanO
    rm = visa.ResourceManager()

PI_Comport = 'com9'
SR830_10_Port = 'GPIB::10::INSTR'
SR830_11_Port = 'GPIB::11::INSTR'


class AppRoot(MultiDataSourceScan):
    dataSaver = Instance(DataSaver)
    
    nMeasurements = Int(1, min=1).tag(name="Number of measurements", priority=99)

    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")
    
    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName=(objectName or 'Time Domain Scan'),
                         loop=loop)
        self.dataSaver = DataSaver(objectName="Data Saver")

        self.pi_conn = PI.Connection(PI_Comport)

        pi_stage = PI.AxisAtController(self.pi_conn)
        pi_stage.objectName = "PI C-863"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        self.manipulator = pi_stage

        self.dataSaver.fileNameTemplate = "Data-{date}-{name}-{dataSource}"
        self.dataSaver.set_trait('path', Path('E:/Messdaten/test'))

        self.sr830_10 = SR830(rm.open_resource(SR830_10_Port), objectName="lockin1")
        self.sr830_11 = SR830(rm.open_resource(SR830_11_Port), objectName="lockin2")

        self.registerDataSource(self.sr830_10)
        self.registerDataSource(self.sr830_11)

        self.continuousScan = True
        self.minimumValue = Q_(350, 'ps')
        self.maximumValue = Q_(375, 'ps')
        self.positioningVelocity = Q_(35, "ps/s")
        self.scanVelocity = Q_(1.6, "ps/s")
        self.step = Q_(0.50, "ps")
        self.overscan = Q_(3, 'ps')
        self.retractAtEnd = True

        self.addDataSetReadyCallback(self.dataSaver.process)
        self.addDataSetReadyCallback(self.setCurrentData)
    
    def setCurrentData(self, dataSet):
        self.set_trait("currentData", dataSet)
    
    @action("Take number of measurements")
    async def takeMultipleMeasurements(self):
        self.set_trait("progress", 0.0)
        for i in range(self.nMeasurements):
            await self.readDataSet()
            val = (i+1) / self.nMeasurements
            self.set_trait("progress", val)

    
    @action("Take measurement")
    async def takeMeasurements(self):
        await self.readDataSet()

    
    async def __aenter__(self):
        await self.pi_conn.__aenter__()
        await self.manipulator.__aenter__()
        await self.sr830_10.__aenter__()
        await self.sr830_11.__aenter__()

        return self
    
    async def __aexit__(self, *args):
        await self.sr830_10.__aexit__(*args)
        await self.sr830_11.__aexit__(*args)
        await self.manipulator.__aexit__(*args)
        await self.pi_conn.__aexit__(*args)
