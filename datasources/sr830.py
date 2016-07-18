# -*- coding: utf-8 -*-
"""
Created on Mon Nov  9 10:32:30 2015

@author: Arno Rehn
"""

import numpy as np
from common import DataSource, DataSet, action, Q_
from asyncioext import threaded_async
from pyvisa import constants
import struct
import enum
from traitlets import Enum, Unicode


class SR830(DataSource):

    class SamplingMode(enum.Enum):
        SingleShot = 0
        Buffered = 1
        ### TODO: support me!
        # Fast = 2

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

    identification = Unicode(read_only=True)
    samplingMode = Enum(SamplingMode, SamplingMode.Buffered).tag(
                        name="Sampling mode")
    sampleRate = Enum(SampleRate, SampleRate.Rate_512_Hz)

    def __init__(self, resource):
        super().__init__()
        self.resource = resource
        self.resource.timeout = 150

    @threaded_async
    def query(self, x):
        return self.resource.query(x)

    async def __aenter__(self):
        await super().__aenter__()
        self.set_trait('identification', await self.query('*IDN?'))
        self._isDualChannel = "SR830" in self.identification

        val = int(await self.query('SRAT?'))
        self.sampleRate = [item for item in SR830.SampleRate
                           if item.value == val][0]

        return self

    @action("Start")
    def start(self):
        self.resource.write('SRAT %d' % self.sampleRate.value)
        if (self.samplingMode == SR830.SamplingMode.Buffered):
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
        prev_read_termination = None
        if self.resource.read_termination is not None:
            prev_read_termination = self.resource.read_termination
            self.resource.read_termination = None

        self.resource.timeout = 10000
        data = self.resource.visalib.read(self.resource.session, size)
        self.resource.timeout = 150

        if prev_read_termination is not None:
            self.resource.read_termination = prev_read_termination
        return data

    @threaded_async
    def readDataBuffer(self):
        nPts = int(self.resource.query('SPTS?'))
        if nPts == 0:
            return []

        if (self._isDualChannel):
            self.resource.write('TRCL? 1,0,%d' % nPts)
        else:
            self.resource.write('TRCL? 0,%d' % nPts)

        data, s = self._readExactly(nPts * 4)
        if (s != constants.StatusCode.success_max_count_read and
            s != constants.StatusCode.success):
            raise Exception("Failed to read complete data set!"
                            "Got %d bytes, expected %d." %
                            (len(data), nPts * 4))
        return SR830._internal2float(data)

    @threaded_async
    def readCurrentOutput(self, channel='X'):
        try:
            idx = ['x', 'y', 'r', 'theta'].index(channel.lower()) + 1
        except ValueError:
            raise ValueError("'{}' is not a valid channel identifier. "
                             "Valid values are: 'x', 'y', 'r', 'theta'."
                             .format(channel))
        return float(self.resource.query('OUTP? %d' % idx))

    async def readDataSet(self):
        if (self.samplingMode == SR830.SamplingMode.SingleShot):
            data = np.array(await self.readCurrentOutput())
            dataSet = DataSet(Q_(data), [])
            return dataSet

        elif (self.samplingMode == SR830.SamplingMode.Buffered):
            data = np.array(await self.readDataBuffer())
            dataSet = DataSet(Q_(data), [Q_(np.arange(0, len(data)))])
            return dataSet
