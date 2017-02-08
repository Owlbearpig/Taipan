# -*- coding: utf-8 -*-
"""
Created on Sun Jan 15 13:51:35 2017

@author: Terahertz
"""

import asyncio
import numpy as np
import traitlets
from common import DataSource, DataSet, action, Q_
from common.traits import DataSet as DataSetTrait, Quantity as QuantityTrait
import PyDAQmx as mx
import logging


class NIDAQ(DataSource):

    active = traitlets.Bool(False, read_only=True).tag(name="Active")

    currentDataSet = DataSetTrait(read_only=True).tag(name="Current chunk",
                                                      data_label="Amplitude",
                                                      axes_labels=["Sample number"])

    analogChannel = traitlets.Unicode('Dev1/ai0', read_only=False)
    clockSource = traitlets.Unicode('', read_only=False)

    voltageMin = QuantityTrait(Q_(-10,'V'))
    voltageMax = QuantityTrait(Q_(10,'V'))

    chunkSize = 2000
    sampleRate = 1e6

    readEveryN = 100

    currentTask = None

    _buf = None
    _cumBuf = np.zeros(0)

    __pendingFutures = []

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)

    def _everyNCallback(self):
        read = mx.int32()
        self.currentTask.ReadAnalogF64(self.readEveryN, 0,  # timeout
                                       mx.DAQmx_Val_GroupByScanNumber,
                                       self._buf, self._buf.size,
                                       mx.byref(read), None)

        # this callback is called from another thread, so we'll post a queued
        # call to the event loop
        chunk = self._buf.copy()
        self._loop.call_soon_threadsafe(lambda: self._handleNewChunk(chunk))

        return 0

    def _taskDone(self, status):
        self.stop()
        return 0

    def _handleNewChunk(self, chunk):
        self._cumBuf = np.concatenate((self._cumBuf, chunk))

        while len(self._cumBuf) >= self.chunkSize:
            properChunk = self._cumBuf[:self.chunkSize].copy()
            self._cumBuf = self._cumBuf[self.chunkSize:].copy()

            axis = np.arange(len(properChunk))

            properChunk = Q_(properChunk, 'V')
            axis = Q_(axis)
            dataSet = DataSet(properChunk, [ axis ])
            self.set_trait('currentDataSet', dataSet)

            for fut in self.__pendingFutures:
                if not fut.done():
                    fut.set_result(dataSet)

            self.__pendingFutures = []

    @action('Start task')
    async def start(self):
        if self.active or self.currentTask is not None:
            raise RuntimeError("Data source is already running")

        self._buf = np.zeros(self.readEveryN)
        self.currentTask = mx.Task()
        self.currentTask.EveryNCallback = self._everyNCallback
        self.currentTask.DoneCallback = self._taskDone

        self.currentTask.CreateAIVoltageChan(self.analogChannel, "",
                                             mx.DAQmx_Val_RSE, -10.0, 10.0,
                                             mx.DAQmx_Val_Volts, None)

        self.currentTask.CfgSampClkTiming(
                self.clockSource, self.sampleRate,
                mx.DAQmx_Val_Rising, mx.DAQmx_Val_ContSamps,
                10 * self.chunkSize # suggested buffer size
        )

        self.currentTask.AutoRegisterEveryNSamplesEvent(
                mx.DAQmx_Val_Acquired_Into_Buffer, self.readEveryN, 0)

        self.currentTask.AutoRegisterDoneEvent(0)
        self.currentTask.StartTask()
        self.set_trait("active", True)

    @action('Stop task')
    async def stop(self):
        if self.currentTask is not None:
            self.currentTask.ClearTask()
            self.currentTask = None
            self.set_trait("active", False)
            self._cumBuf = np.zeros(0)
            logging.info("Task stopped.")

    async def readDataSet(self):
        fut = self._loop.create_future()
        self.__pendingFutures.append(fut)
        dset = await fut
        return dset

if __name__ == '__main__':

    async def main():
        daq = NIDAQ()
        print("Task starting..")
        daq.start()
        print("Task started..")

        await daq.readDataSet()

        print("Got dataset!")

        await asyncio.sleep(5)
        daq.stop()

        print("Quitting")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
