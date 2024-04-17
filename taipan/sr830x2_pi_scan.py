# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, traits, Scan, ureg, Q_, action, MultiDataSourceScan
from common.save import DataSaver
from traitlets import Instance
from pathlib import Path
from stages import PI
from datasources import SR830
import visa
import thz_context
import os


if os.name == 'posix':
    rm = visa.ResourceManager('@py')
elif os.name == 'nt': #JanO
    rm = visa.ResourceManager()

PI_Comport = 'com9'
SR830_10_Port = 'GPIB::10::INSTR'
SR830_11_Port = 'GPIB::11::INSTR'


class AppRoot(MultiDataSourceScan):
    dataSaverDS1 = Instance(DataSaver)
    dataSaverDS2 = Instance(DataSaver)    
    
    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude",
                                 is_power=False)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName=(objectName or 'Time Domain Scan'),
                         loop=loop)
        self.dataSaverDS1 = DataSaver(objectName="Data Saver DS 1")
        self.dataSaverDS2 = DataSaver(objectName="Data Saver DS 2")
        
        self.pi_conn = PI.Connection(PI_Comport)

        pi_stage = PI.AxisAtController(self.pi_conn)
        pi_stage.objectName = "PI C-863"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        self.manipulator = pi_stage
        
        self.dataSaverDS1.fileNameTemplate = "Data-{date}-{name}"
        self.dataSaverDS1.set_trait('path', Path('E:/Messdaten/test'))
        self.dataSaverDS2.fileNameTemplate = "DS2-{date}-{name}"
        self.dataSaverDS2.set_trait('path', Path('E:/Messdaten/test'))
        
        self.sr830_10 = SR830(rm.open_resource(SR830_10_Port), objectName="sr830_10")
        self.sr830_11 = SR830(rm.open_resource(SR830_11_Port), objectName="sr830_11")
        
        self.registerDataSource(self.sr830_10)
        self.registerDataSource(self.sr830_11)

        self.continuousScan = True
        self.set_trait('currentData', DataSet())

        self.minimumValue = Q_(350, 'ps')
        self.maximumValue = Q_(375, 'ps')
        self.positioningVelocity = Q_(35, "ps/s")
        self.scanVelocity = Q_(1.6, "ps/s")
        self.step = Q_(0.50, "ps")
        self.overscan = Q_(3, 'ps')
        self.retractAtEnd = True
        
        self.addDataSetReadyCallback(self.dataSaverDS1.process)
        #self.addDataSetReadyCallback(self.dataSaverDS2.process)
        
        #self.sr830_10.addDataSetReadyCallback(self.setCurrentDataDS1)
        #self.sr830_11.addDataSetReadyCallback(self.setCurrentDataDS2)

    def setCurrentDataDS1(self, dataSet: DataSet):
        dataSet.dataSource = self.sr830_10
        self.set_trait("currentData", dataSet)

    def setCurrentDataDS2(self, dataSet: DataSet):
        dataSet.dataSource = self.sr830_11
        self.set_trait("currentData", dataSet)


    async def __aenter__(self):
        await self.pi_conn.__aenter__()
        await self.manipulator.__aenter__()
        await self.sr830_10.__aenter__()
        await self.sr830_11.__aenter__()
        
        return self

    @action("Take measurement")
    async def takeMeasurements(self):
        await self.readDataSet()

    async def __aexit__(self, *args):
        await self.sr830_10.__aexit__(*args)
        await self.sr830_11.__aexit__(*args)
        await self.manipulator.__aexit__(*args)
        await self.pi_conn.__aexit__(*args)
