# -*- coding: utf-8 -*-
"""
Created on Thu Jul  7 09:17:32 2016

@author: Arno Rehn
"""

import asyncio
from traitlets import Instance, Bool, observe
from common import ComponentBase, Scan, action, Q_
from common.save import DataSaver
from common.avgDataSource import AverageDataSource
from common.traits import DataSet as DataSetTrait
from datasources.tem_fiberstretcher import TEMFiberStretcher
from dummy import DummyManipulator
#from stages.IselStage import IselStage
import sys
import logging

#monsterstage_y = '/dev/serial/by-id/usb-Prolific_Technology_Inc._USB-Serial_Controller-if00-port0'
#monsterstage_x = '/dev/serial/by-id/usb-FTDI_USB_Serial_Converter_FTF2YK31-if00-port0'
tem_serial1 = '/dev/ttyUSB1'
tem_serial2 = '/dev/ttyUSB0'

class AppRoot(Scan):

    dataSaver = Instance(DataSaver)
    resetCounterRow = Bool(True, read_only=False)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName="Y Scan", loop=loop)
        self.title = "Taipan - Schweißgüte 2"

        self.dataSaver = DataSaver(objectName="Data Saver")

        self.tem_fs = TEMFiberStretcher(tem_serial1, tem_serial2,
                                      objectName="TEM FiberStretcher",
                                      loop=loop)

        self.tem_fs.rec_Start = Q_(4,'ps')
        self.tem_fs.rec_Stop = Q_(190,'ps')
        self.tem_fs_av = AverageDataSource(self.tem_fs,objectName="Averager")

        """
        self.manipulatorX = IselStage(monsterstage_x,
                                objectName="Manipulator x",
                                loop=loop)
        """
        self.manipulatorX = DummyManipulator()
        """
        self.manipulatorY = IselStage(monsterstage_y,
                                objectName="Manipulator y",
                                loop=loop)
        """
        self.manipulatorY = DummyManipulator()
        #define the x scan
        self.scanx = Scan(self.manipulatorX, self.tem_fs_av)
        self.scanx.minimumValue=Q_(0,'mm')
        self.scanx.maximumValue=Q_(10,'mm')
        self.scanx.step=Q_(1,'mm')
        self.scanx.scanVelocity = Q_(10,'mm/s')
        self.scanx.positioningVelocity = Q_(100,'mm/s')
        self.scanx.objectName="X Scan"
        self.scanx.retractAtEnd = True
        #define the y scan
        self.dataSource = self.scanx
        self._oldScanXStart = self.dataSource.start
        self._oldScanXStop = self.dataSource.stop
        self.dataSource.start = self.startMotorScan
        self.dataSource.stop = self.stopMotorScan
        self.manipulator = self.manipulatorY
        self.retractAtEnd = True
        self.minimumValue = Q_(0,'mm')
        self.maximumValue = Q_(10,'mm')
        self.step = Q_(2.5, 'mm')
        self.positioningVelocity = Q_(100,'mm/s')
        self.scanVelocity = Q_(10,'mm/s')
        #register the manipulators in the dataSaver
        self.dataSaver.registerManipulator(self.manipulatorX,'X')
        self.dataSaver.registerManipulator(self.manipulatorY,'Y')
        self.dataSaver.fileNameTemplate = '{date}-{name}-{X}-{Y}'
        self.tem_fs_av.addDataSetReadyCallback(self.dataSaver.process)
        self.resetCounter(self.resetCounterRow)

    @observe('resetCounterRow')
    def resetCounter(self,val):
        if isinstance(val,dict):
            val = val['new']
        
        async def start():
            pass
        async def asyncResetCounter():
            self.tem_fs.resetCounter()
        
        if val:
            self.scanx.dataSource.start = asyncResetCounter
        else:
            self.scanx.dataSource.start =  start

    @action("Take single measurement")
    async def takeSingleMeasurement(self):
        data = await self.tem_fs_av.readDataSet()

    @action("Take measurement")
    async def takeMeasurement(self):
        await self.readDataSet()
        #self.dataSaver.process(data)

    async def startMotorScan(self):
        self.tem_fs.mScanEnable = True
        self.tem_fs.resetCounter()
        await self._oldScanXStart()

    async def stopMotorScan(self):
        self.tem_fs.mScanEnable = False
        await self._oldScanXStop()


