# -*- coding: utf-8 -*-
"""
Created on Thu Sep  8 12:21:50 2016

@author: dave
"""
from common import DataSource, action
from traitlets import Integer, Instance
import logging

class AverageDataSource(DataSource):
    numberofAverages = Integer(1,read_only = False).tag(
            name='Number of Averages')

    currentAverages = Integer(0,read_only = True).tag(
            name='current Averages')
    
    dataLen = Integer(0,read_only = True).tag(
            name="Expected Data Length")

    singleSource = Instance(DataSource, allow_none=True)

    def __init__(self, dataSource, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.singleSource = dataSource
    
    def start(self):
        self.singleSource.start()

    def stop(self):
        self.set_trait('currentAverages',1)
        self.singleSource.stop()

    @action("expected length")
    async def readDataLength(self):
        cd = await self.singleSource.readDataSet()
        self.set_trait('dataLen',len(cd.data))

    async def readDataSet(self):
        if self.dataLen == 0:
            logging.info("Please set the expected data length!, try to guess it")
            await self.readDataLength()

        if self.numberofAverages <1:
            logging.info("Averaging: Please insert a positive number, averages set to 1")
            self.numberofAverages = 1
        avDataSet = await self.singleSource.readDataSet()
        while len(avDataSet.data) != self.dataLen:
            logging.info("Failed to read data with correct length, retry!")
            avDataSet = await self.singleSource.readDataSet()
          
        self.set_trait('currentAverages',1)
        while self.currentAverages<self.numberofAverages:
            singleSet = await self.singleSource.readDataSet()
            while len(singleSet.data) != self.dataLen:
                logging.info("Failed to read data with correct length, retry!")
                singleSet = await self.singleSource.readDataSet()

            avDataSet.data += singleSet.data
            self.set_trait('currentAverages',self.currentAverages+1)
        avDataSet.data /= self.numberofAverages
        self._dataSetReady(avDataSet)
        return avDataSet
