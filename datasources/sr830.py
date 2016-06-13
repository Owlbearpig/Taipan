# -*- coding: utf-8 -*-
"""
Created on Mon Nov  9 10:32:30 2015

@author: Arno Rehn
"""

import numpy as np
from common import DataSource, DataSet, action
from asyncioext import threaded_async
from pyvisa import constants
import struct
import enum


class SR830(DataSource):
    def __init__(self, resource):
        super().__init__()
        self.resource = resource
        self.resource.timeout = 150
        self.resource.read_termination = '\n'

    @property
    def identification(self):
        return self.resource.query('*IDN?')

    class SampleRate(enum.Enum):
        Rate_62_5_mHz = 0
        Rate_125_mHz = 1
        Rate_250_mHz = 2
        Rate_500_mHz = 3
        Rate_1_Hz = 4
        Rate_2_Hz = 5
        Rate_4_Hz = 6
        Rate_8_Hz = 7
        Rate_16_Hz = 8
        Rate_32_Hz = 9
        Rate_64_Hz = 10
        Rate_128_Hz = 11
        Rate_256_Hz = 12
        Rate_512_Hz = 13
        Trigger = 14

    def setSampleRate(self, rate):
        self.resource.write('SRAT %d' % rate.value)

    @threaded_async
    def getSampleRate(self):
        val = int(self.resource.query('SRAT?'))
        return [item for item in SR830.SampleRate if item.value == val][0]

    @action("Start")
    def start(self):
        self.resource.write('REST')
        self.resource.write('STRT')

    @action("Stop")
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
        self.resource.read_termination = None
        self.resource.timeout = 10000
        data = self.resource.visalib.read(self.resource.session, size)
        self.resource.timeout = 150
        self.resource.read_termination = '\n'
        return data

    @threaded_async
    def dataPointCount(self):
        return int(self.resource.query('SPTS?'))

    @threaded_async
    def readData(self):
        nPts = int(self.resource.query('SPTS?'))
        if nPts == 0:
            return []
        self.resource.write('TRCL? 0,%d' % nPts)
        data, s = self._readExactly(nPts * 4)
        if (s != constants.StatusCode.success_max_count_read and
            s != constants.StatusCode.success):
            raise Exception("Failed to read complete data set!"
                            "Got %d bytes, expected %d." %
                            (len(data), nPts * 4))
        return SR830._internal2float(data)

    async def readDataSet(self):
        data = np.array(await self.readData())
        dataSet = DataSet(data, [np.arange(0, len(data))])
        return dataSet
