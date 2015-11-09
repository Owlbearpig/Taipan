# -*- coding: utf-8 -*-
"""
Created on Mon Nov  9 10:32:30 2015

@author: Arno Rehn
"""

import numpy as np
from common import DataSource, DataSet
from asyncioext import threaded_async

class SR830(DataSource):
    def __init__(self, resource):
        super().__init__()
        self.resource = resource
        self.resource.timeout = 150
        self.resource.read_termination = '\n'

    def identification(self):
        return self.resource.query('*IDN?')

    def start(self):
        self.resource.write('REST')
        self.resource.write('STRT')

    def stop(self):
        self.resource.write('PAUS')

    @threaded_async
    def readData(self):
        nPts = int(self.resource.query('SPTS?'))
        values = self.resource.query_ascii_values(
                     'TRCA? 1,0,%d' % nPts,
                     separator=lambda data: filter(None, data.split(','))
                 )
        return values

    async def readDataSet(self):
        data = np.array(await self.readData())
        dataSet = DataSet(data, np.arange(0, len(data)))
        return dataSet
