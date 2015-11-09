# -*- coding: utf-8 -*-
"""
Created on Mon Nov  9 10:32:30 2015

@author: Arno Rehn
"""

import numpy as np
from common import DataSource, DataSet
from asyncioext import threaded_async
from pyvisa import constants
import struct

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

    @staticmethod
    def _internal2float(data):
        ret = []
        for i in range(0, len(data), 4):
            m, = struct.unpack('<h', data[i:i+2])
            exp = data[i+2]
            ret.append(m * 2**(exp - 124))
        return ret

    def _readExactly(self, size):
        return self.resource.visalib.read(self.resource.session, size)

    @threaded_async
    def readData(self):
        nPts = int(self.resource.query('SPTS?'))
        self.resource.write('TRCL? 1,0,%d' % nPts)
        data, s = self._readExactly(nPts * 4)
        if s != constants.StatusCode.success_max_count_read:
            raise Exception("Failed to read complete data set!")
        return SR830._internal2float(data)

    async def readDataSet(self):
        data = np.array(await self.readData())
        dataSet = DataSet(data, np.arange(0, len(data)))
        return dataSet
