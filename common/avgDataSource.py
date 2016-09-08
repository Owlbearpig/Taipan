# -*- coding: utf-8 -*-
"""
Created on Thu Sep  8 12:21:50 2016

@author: dave
"""
from common import DataSource
from traitlets import Integer, Instance
import logging

class AverageDataSource(DataSource):
    numberofAverages = Integer(1,read_only = False)
    singleSource = Instance(DataSource, allow_none=True)

    def __init__(self, dataSource, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.singleSource = dataSource
    
    def start(self):
        self.singleSource.start()

    def stop(self):
        self.singleSource.stop()

    async def readDataSet(self):
        if self.numberofAverages <1:
            logging.info("Averaging: Please insert a positive number, averages set to 1")
            self.numberofAverages = 1

        avDataSet = await self.singleSource.readDataSet()
        i=1
        while i<self.numberofAverages:
            singleSet = await self.singleSource.readDataSet()
            avDataSet.data += singleSet.data
            i+=1
        avDataSet.data /= self.numberofAverages
        self._dataSetReady(avDataSet)
        return avDataSet
