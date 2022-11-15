# -*- coding: utf-8 -*-
"""
Created on Wed Mar 22 08:54:13 2017

@author: terahertz
"""
from common import traits, Scan, ureg, Q_, action
from common.save import DataSaver
from stages import PI
from datasources import SR830
import visa
import os
import traitlets
from stages.Goniometer.goniometer import Goniometer
import numpy as np
import asyncio

if os.name == 'posix':
    rm = visa.ResourceManager('@py')
elif os.name == 'nt':
    rm = visa.ResourceManager()
    

PI_Comport = 'COM3'
SR800_Port = 'GPIB0::10::INSTR'


class TimeDomainScan(Scan):


    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude",
                                 is_power=False)

    dataSaver = traitlets.Instance(DataSaver)
    
   
    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName='Goniometer Scan',
                         loop=loop)

        self.dataSaver = DataSaver(objectName="Data Saver")
        self.pi_conn = PI.Connection(PI_Comport)
        
        pi_stage = PI.AxisAtController(self.pi_conn)
        pi_stage.objectName = "PI C-863"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        
        self.manipulator = pi_stage
        self.dataSource = SR830(rm.open_resource(SR800_Port))
        self.dataSource.objectName = "SR830"        
        
        self.continuousScan = True
        self.minimumValue = Q_(1180, 'ps')
        self.maximumValue = Q_(1250, 'ps')
        self.overscan = Q_(3, 'ps')
        self.step = Q_(0.05, 'ps')
        self.positioningVelocity = Q_(30, 'ps/s')
        self.scanVelocity = Q_(1, 'ps/s')

        self.dataSaver.fileNameTemplate = '{date}-{name}'
        self.addDataSetReadyCallback(self.dataSaver.process)
        self._backAndForth = True
        
    def setCurrentData(self, dataSet):
        self.set_trait('currentData', dataSet)
        
    async def __aenter__(self):
        #await super().__aenter__()
        await self.pi_conn.__aenter__()
        await self.manipulator.__aenter__() #pi
        await self.dataSource.__aenter__() #lockin
        
        return self
            
    @action("Take Single measurement")
    async def takeSingleMeasurements(self):
        dataset = await self.TimeDomainScan.readDataSet()
        
    async def __aexit__(self, *args):
        await self.pi_conn.__aexit__(*args)
        await self.manipulator.__aexit__(*args) #pi
        await self.dataSource.__aexit__(*args) #lockin
        await super().__aexit__(*args)

async def run(loop):
    async with Goniometer(1,objectName='Detektor') as detector:
        async with Goniometer(0,objectName='Emitter') as emitter:
            async with TimeDomainScan(loop = loop) as tdscan:
                    
                detector.calibrate(Q_(180.0,'deg'))
                emitter.calibrate(Q_(180.0,'deg'))
                
                for angle in np.arange(10,80,1):
                    emitterpos = 90+angle
                    detectorpos = 270-angle
                    
                    await asyncio.wait([detector.moveTo(Q_(detectorpos,'deg')), 
                                        emitter.moveTo(Q_(emitterpos,'deg'))])
                    print('angle: {}'.format(angle))
                    tdscan.dataSaver.mainFileName = 'Referenz-{}'.format(angle)
                    await tdscan.readDataSet()
                
                await asyncio.wait([detector.moveTo(Q_(180,'deg')), 
                                    emitter.moveTo(Q_(180,'deg'))])
                

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(loop))
    loop.close()