# -*- coding: utf-8 -*-
"""
Created on Sun Jan 15 13:51:35 2017

@author: Terahertz
"""

import numpy as np
import traitlets
from common import DataSource, DataSet, action, Q_, traits
from asyncioext import threaded_async
import enum
import PyDAQmx as mx

class NiDataReader(mx.Task):
    def __init__(self):
        mx.Task.__init__(self)
        self.bufsize = 10000

        self.a = []
        self.CreateAIVoltageChan("Dev4/ai0","",mx.DAQmx_Val_RSE,-10.0,10.0,mx.DAQmx_Val_Volts,None)
        #self.CreateCICountEdgesChan('PFI0','numSaps',mx.DAQmx_Val_Rising,0,mx.DAQmx_Val_CountUp)
        self.CfgSampClkTiming("PFI0",30000.0,mx.DAQmx_Val_Rising,mx.DAQmx_Val_ContSamps,self.bufsize)
        self.AutoRegisterEveryNSamplesEvent(mx.DAQmx_Val_Acquired_Into_Buffer,self.bufsize,0)
        self.AutoRegisterDoneEvent(0)
        self.data = np.zeros((self.bufsize,))
    def EveryNCallback(self):
        read = mx.int32()
        try:
            self.ReadAnalogF64(self.bufsize,10.0,mx.DAQmx_Val_GroupByScanNumber,
                               self.data,self.bufsize,mx.byref(read),None)
        except:
            pass
        self.a.extend(self.data.tolist()[:read.value])
        print('Samps Read: {}'.format(read))
        return 0 # The function should return an integer

    def FinalRead(self):
        read = mx.int32()
        samps = mx.uInt32()

        self.GetReadAvailSampPerChan(mx.byref(samps))
        print(samps.value)

        try:
            self.ReadAnalogF64(self.bufsize,3.0,mx.DAQmx_Val_GroupByScanNumber,
                           self.data,self.bufsize,mx.byref(read),None)
        except:
            pass
        print(read)
        self.a.extend(self.data.tolist()[:read.value])
        return 0 # The function should return an integer

    def DoneCallback(self, status):
        print("Status",status.value)
        return 0 # The function should return an integer


    def getData(self):
        return self.a

class niDAQ(DataSource):
    analogChannel = traitlets.Unicode('ai0',read_only=False)
    triggerChannel = traitlets.Unicode('PFI0',read_only=False)
    minVoltage = traits.Quantity(Q_(-4,'V'))
    maxVoltage = traits.Quantity(Q_(4,'V'))


    def __init__(self, sysDevName = "Dev4", objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)
        self.reader = NiDataReader()
        self.taskRunning = False

    @action('start')
    def start(self):
        self.reader.StartTask()
        self.taskRunning = True

    @action('stop')
    def stop(self):
        if self.taskRunning:
            self.taskRunning = False
            self.reader.FinalRead()
            self.reader.StopTask()


    @action('read')
    async def readDataSet(self):

        data = self.reader.getData()
        self.reader.a = [] #resets data
        return DataSet(Q_(data,'V'),[Q_(np.arange(0, len(data)),'s')])
