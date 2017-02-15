# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2015 - 2016 Arno Rehn <arno@arnorehn.de>

Taipan is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Taipan is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Taipan.  If not, see <http://www.gnu.org/licenses/>.
"""

import numpy as np
from common import DataSource, DataSet, action, Q_
from common.traits import Quantity
from asyncioext import threaded_async, ensure_weakly_binding_future
from threading import Lock
import asyncio
from pyvisa import constants
import struct
import enum
import traitlets
import logging


class SR830(DataSource):

    class SamplingMode(enum.Enum):
        SingleShot = 0
        Buffered = 1
        ### TODO: support me!
        # Fast = 2

    class InputConfiguration(enum.Enum):
        A = 0
        A_B = 1
        I_1MOhm = 2
        I_100MOhm = 3

    class InputShieldGrounding(enum.Enum):
        Float = 0
        Ground = 1

    class InputCoupling(enum.Enum):
        AC_Coupling = 0
        DC_Coupling = 1

    class NotchFilterStatus(enum.Enum):
        NoFilter = 0
        LineNotch = 1
        TwiceLineNotch = 2
        BothNotchFilters = 3

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

    class Sensitivity(enum.Enum):
        Sens_2nV_fA = 0
        Sens_5nV_fA = 1
        Sens_10nv_fA = 2
        Sens_20nv_fA = 3
        Sens_50nv_fA = 4
        Sens_100nv_fA = 5
        Sens_200nv_fA = 6
        Sens_500nv_fA = 7
        Sens_1muV_pA = 8
        Sens_2muV_pA = 9
        Sens_5muV_pA = 10
        Sens_10muV_pA = 11
        Sens_20muV_pA = 12
        Sens_50muV_pA = 13
        Sens_100muV_pA = 14
        Sens_200muV_pA = 15
        Sens_500muV_pA = 16
        Sens_1mV_nA = 17
        Sens_2mV_nA = 18
        Sens_5mV_nA = 19
        Sens_10mV_nA = 20
        Sens_20mV_nA = 21
        Sens_50mV_nA = 22
        Sens_100mV_nA = 23
        Sens_200mV_nA = 24
        Sens_500mV_nA = 25
        Sens_1V_nA = 26

    class TimeConstant(enum.Enum):
        TimeConstant_10mus = 0
        TimeConstant_30mus = 1
        TimeConstant_100mus = 2
        TimeConstant_300mus = 3
        TimeConstant_1ms = 4
        TimeConstant_3ms = 5
        TimeConstant_10ms = 6
        TimeConstant_30ms = 7
        TimeConstant_100ms = 8
        TimeConstant_300ms = 9
        TimeConstant_1s = 10
        TimeConstant_3s = 11
        TimeConstant_10s = 12
        TimeConstant_30s = 13
        TimeConstant_100s = 14
        TimeConstant_300s = 15
        TimeConstant_1ks = 16
        TimeConstant_3ks = 17
        TimeConstant_10ks = 18
        TimeConstant_30ks = 19

    class ReserveMode(enum.Enum):
        HighReserve = 0
        Normal = 1
        LowNoise = 2

    class LowPassFilterSlope(enum.Enum):
        FilterSlope6dB_oct = 0
        FilterSlope12dB_oct = 1
        FilterSlope18dB_oct = 2
        FilterSlope24dB_oct = 3

    class ReferenceSource(enum.Enum):
        External = 0
        Internal = 1

    class ReferenceTrigger(enum.Enum):
        SineZeroCrossing = 0
        TTL_rising_edge = 1
        TTL_falling_edge = 2

    class StatusBits(enum.Enum):
        NoScanInProgress = 0x1  #keep in mind that in PAUS this is False
        NoCommandExecutionInProgress = 0x2
        ErrorOccured = 0x4
        LIAOccured = 0x8
        InterfaceOutputBufferNotEmpty = 0x10
        EventOccured = 0x20
        ServiceRequest = 0x40

    class StandardEventBits(enum.Enum):
        InputQueueOverflow = 0x1
        OutputQueueOverflow = 0x4
        ParameterOutOfRange = 0x10
        IllegalCommand = 0x20
        KeyPressed = 0x40
        PowerOn = 0x80

    class LIABits(enum.Enum):
        InputorAmplitudeOverload = 0x1
        TimeConstantFilterOverload = 0x2
        OutputOverload = 0x4
        ReferenceUnlock = 0x8
        DetectionRangeSwitch = 0x10
        ImplicitTimeConstantChange = 0x20
        DataStorageTriggeredExternally = 0x40

    class ErrorBits(enum.Enum):
        BackupError = 0x2
        RAMError = 0x4
        ROMError = 0x10
        GPIBError = 0x20
        DSPError = 0x40
        MathError = 0x80

    class SynchronousFilterStatus(enum.Enum):
        Off = 0
        On = 1

    statusmessages = {
        'status': {0x1: 'Input or Amplifier overload is detected!',
                   0x2: 'Time Constant filter overload detected!',
                   0x4: 'Output overload detected!',
                   0x8: 'Reference unlock detected!',
                   0x10: 'Detection frequency switched ranges.',
                   0x20: 'Time constant is changed indirectly, either by ' +
                   'changing frequency range, dynamic reserve, filter' +
                   'slope or expand.',
                   0x40: 'Data storage was triggered'},
        'errors': {0x2: 'Battery backup has failed after Power up',
                   0x4: 'RAM Memory test found an error.',
                   0x10: 'ROM Memory test found an error.',
                   0x20: 'GPIB fast data transfer mode aborted.',
                   0x40: 'DSP test found an error.',
                   0x80: 'Internal math error occured.'},
        'events': {0x1: 'Input queue overflow (too many commands received at' +
                       ' once, queues cleared).',
                   0x4: 'Output queue overflow (too many responses waiting ' +
                   'to be transmitted, queues cleared).',
                   0x10: 'Command can not execute correctly or a parameter' +
                   ' is out of range.',
                   0x20: 'Illegal command received',
                   0x40: 'Any key press or knob rotation!',
                   0x80: 'Set by Power on'}
    }

#    general traits
    identification = traitlets.Unicode(read_only=True)

    samplingMode = traitlets.Enum(SamplingMode, SamplingMode.Buffered).tag(
                        name="Sampling mode")

    sampleRate = traitlets.Enum(SampleRate, SampleRate.Rate_512_Hz)
    sampleRate.tag(command='SRAT')

#    REFERENCE and PHASE Commands
    referencePhase = Quantity(Q_(0, 'deg'), min=Q_(-360.0, 'deg'),
                              max=Q_(729.99, 'deg'), read_only=False)
    referencePhase.tag(name='Reference Phase', command='PHAS',
                       group='Reference and Phase Settings')

    referenceSource = traitlets.Enum(ReferenceSource,
                                     ReferenceSource.External)
    referenceSource.tag(name='Reference Source', command='FMOD',
                        group='Reference and Phase Settings')

    referenceFrequency = Quantity(Q_(10, 'Hz'), min=Q_(0.0001, 'Hz'),
                                  max=Q_(102000, 'Hz'), read_only=False)
    referenceFrequency.tag(name='Reference Frequency', command='FREQ',
                           group='Reference and Phase Settings')

    referenceTrigger = traitlets.Enum(ReferenceTrigger,
                                      ReferenceTrigger.SineZeroCrossing)
    referenceTrigger.tag(name='Reference Trigger', command='RSLP',
                         group='Reference and Phase Settings')

    detectionHarmonic = traitlets.Integer(1, min=1, max=19999,
                                          read_only=False)
    detectionHarmonic.tag(name='ith harmonic of reference frequency',
                          command='HARM',
                          group='Reference and Phase Settings')

    sineOutputAmplitude = Quantity(Q_(0.004, 'V'), min=Q_(0.004, 'V'),
                                   max=Q_(5, 'V'), read_only=False)
    sineOutputAmplitude.tag(name='Sine Output Amplitude', command='SLVL',
                            group='Reference and Phase Settings')
#   #INPUT and FILTER COMMANDS
    inputConfiguration = traitlets.Enum(InputConfiguration,
                                        InputConfiguration.A)
    inputConfiguration.tag(name='Input Configuration', command='ISRC',
                           group='Input and Filter Settings')

    inputShieldGrounding = traitlets.Enum(InputShieldGrounding,
                                          InputShieldGrounding.Float)
    inputShieldGrounding.tag(name='Input Shield Grounding',
                             command='IGND',
                             group='Input and Filter Settings')

    inputCoupling = traitlets.Enum(InputCoupling, InputCoupling.AC_Coupling)
    inputCoupling.tag(name='Input Coupling', command='ICPL',
                      group='Input and Filter Settings')

    notchFilterStatus = traitlets.Enum(NotchFilterStatus,
                                       NotchFilterStatus.NoFilter)
    notchFilterStatus.tag(name='Notch Filters', command='ILIN',
                          group='Input and Filter Settings')

#    AUX INPUT & OUTPUT #how to treat those?
    auxInput1 = Quantity(Q_(0, 'V'), read_only=True)
    auxInput1.tag(group='AUX', command='OAUX')
    auxInput2 = Quantity(Q_(0, 'V'), read_only=True)
    auxInput2.tag(group='AUX', command='OAUX')
    auxInput3 = Quantity(Q_(0, 'V'), read_only=True)
    auxInput3.tag(group='AUX', command='OAUX')
    auxInput4 = Quantity(Q_(0, 'V'), read_only=True)
    auxInput4.tag(group='AUX', command='OAUX')

    auxOutput1 = Quantity(Q_(0, 'V'), min=Q_(-10.5, 'V'), max=Q_(10.5, 'V'))
    auxOutput1.tag(group='AUX', command='AUXV')
    auxOutput2 = Quantity(Q_(0, 'V'), min=Q_(-10.5, 'V'), max=Q_(10.5, 'V'))
    auxOutput2.tag(group='AUX', command='AUXV')
    auxOutput3 = Quantity(Q_(0, 'V'), min=Q_(-10.5, 'V'), max=Q_(10.5, 'V'))
    auxOutput3.tag(group='AUX', command='AUXV')
    auxOutput4 = Quantity(Q_(0, 'V'), min=Q_(-10.5, 'V'), max=Q_(10.5, 'V'))
    auxOutput4.tag(group='AUX', command='AUXV')

#   GAIN and TIME CONSTANT COMMANDS
    timeConstant = traitlets.Enum(TimeConstant,
                                  TimeConstant.TimeConstant_10mus)
    timeConstant.tag(name="Time Constant", command='OFLT',
                     group='Gain and Time constant Settings')

    sensitivity = traitlets.Enum(Sensitivity,
                                 Sensitivity.Sens_2nV_fA)
    sensitivity.tag(name="Sensitivity", command='SENS',
                    group='Gain and Time constant Settings')

    reserveMode = traitlets.Enum(ReserveMode,
                                 ReserveMode.HighReserve)
    reserveMode.tag(name='Reserve Mode', command='RMOD',
                    group='Gain and Time constant Settings')

    lowPassFilterSlope = traitlets.Enum(LowPassFilterSlope,
                                        LowPassFilterSlope.FilterSlope6dB_oct)
    lowPassFilterSlope.tag(name='Low Pass Filter Slope', command='OFSL',
                           group='Gain and Time constant Settings')

    synchronousFilterStatus = traitlets.Enum(SynchronousFilterStatus,
                                             SynchronousFilterStatus.On,
                                             read_only=False)
    synchronousFilterStatus.tag(name='Synchronous Filters', command='SYNC',
                                group='Gain and Time constant Settings')

#   status traits
    scanInProgress = traitlets.Bool(False, read_only=True).tag(
            group='Status')
    commandExecutionInProgress = traitlets.Bool(False, read_only=True).tag(
            group='Status')
    errorOccured = traitlets.Bool(False, read_only=True).tag(
            group='Status')
    lockInStatusReport = traitlets.Bool(False, read_only=True).tag(
            group='Status')
    interfaceOutputBuffer = traitlets.Bool(False, read_only=True).tag(
            group='Status')
    eventOccured = traitlets.Bool(False, read_only=True).tag(
            group='Status')
    serviceRequest = traitlets.Bool(False, read_only=True).tag(
            group='Status')

#    configuration traits
    saveSettings = traitlets.Integer(1, min=1, max=9)
    saveSettings.tag(name='Save Settings to Lock-in',
                     group='Configuration')

    loadSettings = traitlets.Integer(1, min=1, max=9)
    loadSettings.tag(name='Load Settings from Lock-in',
                     group='Configuration')

    def __init__(self, resource, objectName=None, loop=None):
        super().__init__(objectName=None, loop=None)
        self.resource = resource
        self.resource.timeout = 1000
        self.observe(self.setParameter, traitlets.All)
        self._traitChangesDueToStatusUpdate = True
        self._lock = Lock()
        self._statusUpdateFuture = ensure_weakly_binding_future(
                                                    self.contStatusUpdate)

    async def __aenter__(self):
        await super().__aenter__()
        self.set_trait('identification', await self.query('*IDN?'))
        self._isDualChannel = "SR830" in self.identification

#       configure the status bit event registers
        self.clearStatus()
#       deactivates start trigger
        asyncio.ensure_future(self.write('TSTR 0'))
#        report all LIAS bits except the dataacquistion triggered flag
        asyncio.ensure_future(self.write('LIAE 191'))
        asyncio.ensure_future(self.write('ERRE 255'))  #report all Errors
        asyncio.ensure_future(self.write('*ESE 255'))  #report all Events
        await self.readAllParameters()
        await self.statusUpdate()
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._statusUpdateFuture.cancel()

    @threaded_async
    def query(self, command):
        with self._lock:
            res = self.resource.query(command)
            iters = 0
            while len(res) == 0 or res[-1] != '\n' and iters < 10:
                res += self.resource.read()
                iters += 1
            if iters == 10:
                logging.info('Fatal error, command did not result in ' +
                             'correct reply')
            return res

    @threaded_async
    def write(self, command, lock=True):
        logging.info('{}: {}'.format(self, command))
        if lock:
            with self._lock:
                return self.resource.write(command)
        else:
            return self.resource.write(command)

    @action("Start")
    async def start(self):
        if (self.samplingMode == SR830.SamplingMode.Buffered):
            await self.write('REST')
#           Only for triggered STRT ist neccessary
            if self.sampleRate == SR830.SampleRate.Trigger:
                await self.write('STRT')

    @action("Stop")
    async def stop(self):
        await self.write('PAUS')

    def reset(self):
        asyncio.ensure_future(self.write('*RST'))
        asyncio.ensure_future(self.readAllParameters())

    async def readAllParameters(self):
        self._traitChangesDueToStatusUpdate = True
        
        for name, trait in self.traits().items():
            command = trait.metadata.get('command')

            if command is None:
                continue
            else:
                auxs = ''
                if command.find('AUX') >= 0:
                    auxs = ' ' + name[-1]
                result = await self.query(command + '?'+auxs)

            if isinstance(trait, traitlets.Enum):
                val = int(result)
                val = [item for item in trait.values if item.value == val][0]
            elif isinstance(trait, Quantity):
                val = Q_(float(result), trait.default_value.units)
            elif isinstance(trait, traitlets.Integer):
                val = int(result)

            self.set_trait(name, val)

        self._traitChangesDueToStatusUpdate = False
        logging.info('SR830: Lockin-Parameter read')

# this is the function that is called by all traits that get observed
    def setParameter(self, change):
        if self._traitChangesDueToStatusUpdate:
            return

        trait = self.traits().get(change['name'])
        command = trait.metadata.get('command')
        value = change['new']

        if command is None:
            return

        self.set_trait(trait.name, value)

        if isinstance(value, enum.Enum):
            value = value.value
        elif isinstance(value, Q_):
            value = value.magnitude

        if command.find('AUX') >= 0:
            channel = trait.name[-1]
            asyncio.ensure_future(
                self.write(command + ' {}, {:.3f}'.format(channel, value)))
        else:
            asyncio.ensure_future(
                    self.write(command + ' {}'.format(value)))

    @action('Auto Gain', group='Auto Functions')
    def autoGain(self):
        asyncio.ensure_future(self.write('AGAN'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Phase', group='Auto Functions')
    def autoPhase(self):
        asyncio.ensure_future(self.write('APHS'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Reserve', group='Auto Functions')
    def autoReserve(self):
        asyncio.ensure_future(self.write('ARSV'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Offset', group='Auto Functions')
    def autoOffset(self, channel=1):
        ''''channel=1: X, channel=2: Y, channel=3: R'''
        asyncio.ensure_future(self.write('AOFF %d' % channel))
        asyncio.ensure_future(self.readAllParameters())

    def clearStatus(self):
        asyncio.ensure_future(self.write('*CLS'))

    async def contStatusUpdate(self):
        while True:
            await asyncio.sleep(1)
            await self.statusUpdate()

    async def statusUpdate(self):
        status = int(await self.query('*STB?'))
        self.set_trait('scanInProgress',
                       not bool(status &
                                SR830.StatusBits.NoScanInProgress.value))
        self.set_trait('commandExecutionInProgress',
                       not bool(status &
                       SR830.StatusBits.NoCommandExecutionInProgress.value))
        self.set_trait('errorOccured',
                       bool( status & SR830.StatusBits.ErrorOccured.value))
        self.set_trait('lockInStatusReport',
                       bool( status & SR830.StatusBits.LIAOccured.value))
        self.set_trait('interfaceOutputBuffer',
                       bool( status & SR830.StatusBits.InterfaceOutputBufferNotEmpty.value))
        self.set_trait('eventOccured',
                       bool(status & SR830.StatusBits.EventOccured.value))
        self.set_trait('serviceRequest',
                       bool(status & SR830.StatusBits.ServiceRequest.value))

        if self.lockInStatusReport:
            lias = int(await self.query('LIAS?'))
            ststr = 'SR830: Lock-in Status Report: '
            for b in SR830.LIABits:
                if bool(lias & b.value):
                    logging.info(ststr + SR830.statusmessages['status'][b.value])

        if self.errorOccured:
            error = int(await self.query('ERRS?'))
            ststr = 'SR830: Lock in Error Report: '
            for b in SR830.ErrorBits:
                if bool(error & b.value):
                    logging.info(ststr + SR830.statusmessages['error'][b.value])

        if self.eventOccured:
            event = int(await self.query('*ESR?'))
            ststr = 'SR830: Lock In Standard Event Report: '
            for b in SR830.StandardEventBits:

                if bool(event & b.value):
                    logging.info(ststr + SR830.statusmessages['event'][b.value])

            if bool(event & SR830.StandardEventBits.KeyPressed.value):
                logging.info('SR830: Reading all Lockin-Parameters')
                await self.readAllParameters()

    @traitlets.observe('saveSettings')
    def saveSettingsToLockin(self, val):
        if isinstance(val, dict):
            val = val['new']
        asyncio.ensure_future(self.write('SSET %d' % val))

    @traitlets.observe('loadSettings')
    def loadSettingsFromLockin(self, val):
        if isinstance(val, dict):
            val = val['new']
        asyncio.ensure_future(self.write('RSET %d' % val))
        asyncio.ensure_future(self.readAllParameters())

    @staticmethod
    def _internal2float(data):
        ret = []
        for i in range(0, len(data), 4):
            m, = struct.unpack('<h', data[i:i+2])
            exp = data[i+2]
            ret.append(m * 2**(exp - 124))
        return ret

    @threaded_async
    def _readExactly(self, size):
        prev_read_termination = None
        if self.resource.read_termination is not None:
            prev_read_termination = self.resource.read_termination
            self.resource.read_termination = None

        prev_timeout = self.resource.timeout
        self.resource.timeout = 40000

        print('Read now lockin with visalib')
        data = self.resource.visalib.read(self.resource.session, size)
        self.resource.timeout = prev_timeout

        if prev_read_termination is not None:
            self.resource.read_termination = prev_read_termination
        return data

    async def readDataBuffer(self):
        nPts = int(await self.query('SPTS?'))
        if nPts == 0:
            return []
        with self._lock:
            if (self._isDualChannel):
                await self.write('TRCL? 1,0,%d' % nPts, lock=False)
            else:
                await self.write('TRCL? 0,%d' % nPts, lock=False)

            data, s = await self._readExactly(nPts * 4)
        if (s != constants.StatusCode.success_max_count_read and
            s != constants.StatusCode.success):
            raise Exception("Failed to read complete data set!"
                            "Got %d bytes, expected %d." %
                            (len(data), nPts * 4))
        return SR830._internal2float(data)

    async def readCurrentOutput(self, channel='X'):
        try:
            idx = ['x', 'y', 'r', 'theta'].index(channel.lower()) + 1
        except ValueError:
            raise ValueError("'{}' is not a valid channel identifier. "
                             "Valid values are: 'x', 'y', 'r', 'theta'."
                             .format(channel))
        return float(await self.query('OUTP? %d' % idx))

    async def readDataSet(self):
        if (self.samplingMode == SR830.SamplingMode.SingleShot):
            data = np.array(await self.readCurrentOutput())
            dataSet = DataSet(Q_(data), [])
            self._dataSetReady(dataSet)
            return dataSet

        elif (self.samplingMode == SR830.SamplingMode.Buffered):
            data = np.array(await self.readDataBuffer())
            dataSet = DataSet(Q_(data), [Q_(np.arange(0, len(data)))])
            self._dataSetReady(dataSet)
            return dataSet
