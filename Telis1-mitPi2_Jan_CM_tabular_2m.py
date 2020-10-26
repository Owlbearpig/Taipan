# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, traits, Scan, ureg, Q_, action, TabularMeasurements2M
from common.save import DataSaver
from stages import PI
from stages.tmcl_JanO import TMCL
from datasources import SR830
import visa
import thz_context
import os
import traitlets
from pathlib import Path

if os.name == 'posix':
    rm = visa.ResourceManager('@py')
elif os.name == 'nt':
    rm = visa.ResourceManager()
    
PI_Comport = 'COM4'
PI_Manipulator = 'COM3'
tmcl_port = 'COM5'

SR800_Port = 'GPIB0::10::INSTR'

class AppRoot(TabularMeasurements2M):

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude",
                                 is_power=False)

    dataSaver = traitlets.Instance(DataSaver)

    nMeasurements = traitlets.Int(1, min=1).tag(name="No. of measurements", priority=99)
   
    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName='PI tabular measurements',
                         loop=loop)

        self.dataSaver = DataSaver(objectName="Data Saver")
        
        self.pi_conn = PI.Connection(PI_Comport)
        self.mani_conn = PI.Connection(PI_Manipulator)
    
        pi_stage = PI.AxisAtController(self.pi_conn, ignore216 = True)# ignore216 implemented by JanO Warning!
        pi_stage.objectName = "PI C-863 DLine"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        
        self.TimeDomainScan = Scan(objectName='TimeDomainScan')
        self.TimeDomainScan.manipulator = pi_stage
        self.TimeDomainScan.dataSource = SR830(rm.open_resource(SR800_Port))
        self.TimeDomainScan.dataSource.objectName = "SR830"        
        
        self.TimeDomainScan.continuousScan = True
        self.TimeDomainScan.minimumValue = Q_(1250, 'ps')
        self.TimeDomainScan.maximumValue = Q_(1315, 'ps')
        self.TimeDomainScan.overscan = Q_(3, 'ps')
        self.TimeDomainScan.step = Q_(0.05, 'ps')
        self.TimeDomainScan.positioningVelocity = Q_(30, 'ps/s')
        self.TimeDomainScan.scanVelocity = Q_(1.6, 'ps/s')
        self.TimeDomainScan.retractAtEnd = True

        self.dataSource = self.TimeDomainScan
        
        manipulator1 = PI.AxisAtController(self.mani_conn, ignore216 = True) # ignore216 implemented by JanO Warning!
        # ignore216 = True means that the error 216 (driven into end switch) will be ignored. There is a problem with the
        # PI stage being used as a manipulator. It is showing this error despite being far away form the end siwtch or even not moving
        manipulator1.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)   # added JanO 22.1.2019   
        manipulator1.objectName='PI C-863'
        self.manipulator1 = manipulator1
        self.positioningVelocityM1 = Q_(4, 'mm/s')
        self.scanVelocity = Q_(4, 'mm/s')
        
        manipulator2 = TMCL(objectName="TMCL Rotator", port=tmcl_port)
        manipulator2.setPreferredUnits(ureg.deg, ureg.dimensionless) # ureg.dimensionless, ureg.mm / ureg.s
        self.manipulator2 = manipulator2
        
        self.dataSaver.registerManipulator(self.manipulator1, 'Position')
        self.dataSaver.registerManipulator(self.manipulator2, 'Rotation')
        self.dataSaver.registerObjectAttribute(self, 'currentMeasurementName', 'currentTableEntry')
        self.dataSaver.fileNameTemplate = '{date}-{name}-{currentTableEntry}-{Position}-{Rotation}'
        self.dataSaver.set_trait('path',Path('E:/Messdaten/test/')) #added by Cornelius as standard savepath
        self.TimeDomainScan.addDataSetReadyCallback(self.dataSaver.process)
        self.TimeDomainScan.addDataSetReadyCallback(self.setCurrentData)
        self._backAndForth = True
        
    def setCurrentData(self, dataSet):
        self.set_trait('currentData', dataSet)
        
    async def __aenter__(self):
        #await super().__aenter__()
        await self.pi_conn.__aenter__()
        await self.mani_conn.__aenter__()
        await self.manipulator1.__aenter__()
        await self.manipulator2.__aenter__()
        await self.TimeDomainScan.manipulator.__aenter__() #pi
        await self.TimeDomainScan.dataSource.__aenter__() #lockin

        return self
            
    @action("Take Tabular measurements")
    async def takeangleScan(self):
        self.set_trait('progress2',0)#progress trait changes added by Cornelius for additional progress Information
        for x in range(self.nMeasurements):
            dataset = await self.readDataSet()
            self.set_trait('progress2',(x+1)/self.nMeasurements)
    
    @action("Take No. of measurements")
    async def takeSingleMeasurements(self):
        self.set_trait('progress',0) #progress trait changes added by Cornelius for additional progress Information
        self.set_trait('progress2',0)
        for x in range(self.nMeasurements):
            dataset = await self.TimeDomainScan.readDataSet()
            self.set_trait('progress',(x+1)/self.nMeasurements)
            self.set_trait('progress2',(x+1)/self.nMeasurements)
    
    @action("Stop")
    async def stop(self): # added by Cornelius to Stop both tabular scan and multiple measurements scan
        if not self._activeFuture:
            if not self.TimeDomainScan._activeFuture:
                return
            self.TimeDomainScan._activeFuture.cancel()
            return
        self._activeFuture.cancel()
        
    async def __aexit__(self, *args):
        await self.pi_conn.__aexit__(*args)
        await self.mani_conn.__aexit__(*args)
        await self.manipulator1.__aexit__(*args)
        await self.manipulator2.__aexit__(*args)
        await self.TimeDomainScan.manipulator.__aexit__(*args) #pi
        await self.TimeDomainScan.dataSource.__aexit__(*args) #lockin
        await super().__aexit__(*args)
