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
from asyncioext import threaded_async,ensure_weakly_binding_future
import asyncio
from pyvisa import constants
import struct
import enum
import traitlets
import logging

#from traitlets import Enum, Unicode, Bool

class SR830(DataSource):

    class SamplingMode(enum.Enum):
        SingleShot = 0
        Buffered = 1
        ### TODO: support me!
        # Fast = 2

    class InputConfiguration(enum.Enum):
        A = 0
        A_B= 1
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
        NoScanInProgress = 0x1
        NoCommandExecutionInProgress = 0x2
        ErrorOccured = 0x4
        ExtendedStatusBitSet = 0x8
        InterfaceOutputBufferNotEmpty = 0x10
        AnEnabledBitHasBeenSet = 0x20
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

    #general traits
    identification = traitlets.Unicode(read_only=True)
    samplingMode = traitlets.Enum(SamplingMode, SamplingMode.Buffered).tag(
                        name="Sampling mode")
    sampleRate = traitlets.Enum(SampleRate, SampleRate.Rate_512_Hz)

    #REFERENCE and PHASE Commands
    referencePhase = Quantity(Q_(0,'deg'),read_only = False)
    referencePhase.tag(name = 'Reference Phase',
                       group = 'Reference and Phase Settings')
    referenceSource = traitlets.Enum(ReferenceSource,
                                     ReferenceSource.External)
    referenceSource.tag(name = 'Reference Source',
                        group = 'Reference and Phase Settings')
    referenceFrequency = Quantity(Q_(0,'Hz'), read_only = False)
    referenceFrequency.tag(name = 'Reference Frequency',
                           group='Reference and Phase Settings')
    referenceTrigger = traitlets.Enum(ReferenceTrigger,
                    ReferenceTrigger.SineZeroCrossing)
    referenceTrigger.tag(name = 'Reference Trigger',
                         group='Reference and Phase Settings')
    detectionHarmonic = traitlets.Integer(1, read_only = False)
    detectionHarmonic.tag(name = 'ith harmonic of reference frequency',
                          group='Reference and Phase Settings')
    sineOutputAmplitude = Quantity(Q_(0,'V'), read_only = False)
    sineOutputAmplitude.tag(name = 'Sine Output Amplitude',
                            group='Reference and Phase Settings')

    #INPUT and FILTER COMMANDS
    inputConfiguration = traitlets.Enum(InputConfiguration,
                                        InputConfiguration.A)
    inputConfiguration.tag(name = 'Input Configuration',
                           group = 'Input and Filter Settings')
    inputShieldGrounding = traitlets.Enum(InputShieldGrounding,
                                          InputShieldGrounding.Float)
    inputShieldGrounding.tag(name = 'Input Shield Grounding',
                             group = 'Input and Filter Settings')
    inputCoupling = traitlets.Enum(InputCoupling, InputCoupling.AC_Coupling)
    inputCoupling.tag(name = 'Input Coupling',
                      group = 'Input and Filter Settings')
    notchFilterStatus = traitlets.Enum(NotchFilterStatus,NotchFilterStatus.NoFilter)
    notchFilterStatus.tag(name = 'Notch Filters',
                          group = 'Input and Filter Settings')

    #GAIN and TIME CONSTANT COMMANDS
    timeConstant = traitlets.Enum(TimeConstant,
                                  TimeConstant.TimeConstant_10mus)
    timeConstant.tag(name="Time Constant",
                     group = 'Gain and Time constant Settings')

    sensitivity = traitlets.Enum(Sensitivity,
                                 Sensitivity.Sens_2nV_fA)
    sensitivity.tag(name="Sensitivity",
                    group = 'Gain and Time constant Settings')
    reserveMode = traitlets.Enum(ReserveMode,
                                 ReserveMode.HighReserve)
    reserveMode.tag(name='Reserve Mode',
                    group = 'Gain and Time constant Settings')
    lowPassFilterSlope = traitlets.Enum(LowPassFilterSlope,
                                        LowPassFilterSlope.FilterSlope6dB_oct)
    lowPassFilterSlope.tag(name = 'Low Pass Filter Slope',
                           group = 'Gain and Time constant Settings')
    synchronousFilterStatus = traitlets.Bool(False, read_only=False)
    synchronousFilterStatus.tag(name='Synchronous Filters',
                                group = 'Gain and Time constant Settings')


    #status traits
    scanInProgress = traitlets.Bool(False, read_only=True).tag(
            group = 'Status')
    commandExecutionInProgress = traitlets.Bool(False, read_only=True).tag(
            group = 'Status')
    errorOccured = traitlets.Bool(False, read_only=True).tag(
            group = 'Status')
    extendedBitSet = traitlets.Bool(False, read_only = True).tag(
            group = 'Status')
    interfaceOutputBuffer = traitlets.Bool(False, read_only = True).tag(
            group = 'Status')
    enabledBitSet = traitlets.Bool(False, read_only = True).tag(
            group = 'Status')
    serviceRequest = traitlets.Bool(False, read_only = True).tag(
            group = 'Status')

    #liveView Traits

    liveViewValueX = Quantity(Q_(0,'pV'),read_only = True)
    liveViewValueX.tag(name = 'X',
                       group = 'Live View')
    
    liveViewValueY = Quantity(Q_(0,'pV'),read_only = True)
    liveViewValueY.tag(name = 'Y',
                       group = 'Live View')

    liveViewValueR = Quantity(Q_(0,'pV'),read_only = True)
    liveViewValueR.tag(name = 'R',
                       group = 'Live View')
    
    liveViewValueTheta = Quantity(Q_(0,'deg'),read_only = True)
    liveViewValueTheta.tag(name = 'Current Value',
                       group = 'Live View')
    
    liveViewValueRefF = Quantity(Q_(0,'kHz'),read_only = True)
    liveViewValueRefF.tag(name = 'Reference F',
                       group = 'Live View')
    
    liveViewMaxValue = Quantity(Q_(0,'pV'),read_only = True)
    liveViewMaxValue.tag(name = 'Max Value',
                       group = 'Live View')
    liveViewMinValue = Quantity(Q_(0,'pV'),read_only = True)
    liveViewMinValue.tag(name = 'Min Value',
                       group = 'Live View')
    
    #configuration traits
    saveSettings = traitlets.Integer(1, min=1, max=9).tag(
            name = 'Save Settings to Lock-in', group = 'Configuration')
    loadSettings = traitlets.Integer(1, min=1, max=9).tag(
            name = 'Load Settings from Lock-in', group = 'Configuration')

    def __init__(self, resource):
        super().__init__()
        self.resource = resource
        self.resource.timeout = 1500
        self._liveViewFuture = asyncio.Future()
        self._liveViewFuture.set_result(True)

    @threaded_async
    def query(self, x):
        return self.resource.query(x)

    async def __aenter__(self):
        await super().__aenter__()
        self.set_trait('identification', await self.query('*IDN?'))
        self._isDualChannel = "SR830" in self.identification

        self.getSampleRate()
        self.observe(self.setSampleRate,'sampleRate')
        self.getTimeConstant()
        self.observe(self.setTimeConstant,'timeConstant')
        self.getSensitivity()
        self.observe(self.setSensitivity,'sensitivity')
        self.getReserveMode()
        self.observe(self.setReserveMode,'reserveMode')
        self.getLowPassFilterSlope()
        self.observe(self.setLowPassFilterSlope, 'lowPassFilterSlope')
        self.getSynchronousFilterStatus()
        self.observe(self.setSynchronousFilterStatus,'synchronousFilterStatus')
        self.getInputConfiguration()
        self.observe(self.setInputConfiguration,'inputConfiguration')        
        self.getInputShieldGrounding()
        self.observe(self.setInputShieldGrounding,'inputShieldGrounding')
        self.getInputCoupling()
        self.observe(self.setInputCoupling,'inputCoupling')
        self.getNotchFilterStatus()
        self.observe(self.setNotchFilterStatus,'notchFilterStatus')
        self.getReferencePhase()
        self.observe(self.setReferencePhase,'referencePhase')
        self.getReferenceSource()
        self.observe(self.setReferenceSource,'referenceSource')
        self.getReferenceFrequency()
        self.observe(self.setReferenceFrequency,'referenceFrequency')
        self.getReferenceTrigger()
        self.observe(self.setReferenceTrigger,'referenceTrigger')
        self.getDetectionHarmonic()
        self.observe(self.setDetectionHarmonic,'detectionHarmonic')
        self.getSineOutputAmplitude()
        self.observe(self.setSineOutputAmplitude,'sineOutputAmplitude')

        await self.statusUpdate()
        return self

    async def __aexit__(self,*args):
        await super().__aexit__(*args)
        self._liveViewFuture.cancel()
        
    @action("Start")
    async def start(self):
        self.resource.write('SRAT %d' % self.sampleRate.value)
        if (self.samplingMode == SR830.SamplingMode.Buffered):
            self.resource.write('REST')
            self.resource.write('STRT')

    @action("Stop")
    async def stop(self):
        self.resource.write('PAUS')

    @action('Reset')
    async def reset(self):
        self.resource.write('*RST')
    
    def setSampleRate(self,sampleRate):
        if isinstance(sampleRate,dict):
            sampleRate = sampleRate['new']
        self.resource.write('SRAT %d' % sampleRate.value)
        self.set_trait('sampleRate',sampleRate)

    def getSampleRate(self):
        val = int(self.resource.query('SRAT?'))
        item = [item for item in SR830.SampleRate
                           if item.value == val][0]
        self.set_trait('sampleRate',item)
        return self.sampleRate
        
    def setTimeConstant(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('OFLT %d' % val.value)
        self.set_trait('timeConstant',val)

    def getTimeConstant(self):
        val = int(self.resource.query('OFLT?'))
        item = [item for item in SR830.TimeConstant
                           if item.value == val][0]

        self.set_trait('timeConstant' , item)
        return self.timeConstant

    def setSensitivity(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('SENS %d' % val.value)
        self.set_trait('sensitivity',val)

    def getSensitivity(self):
        val = int(self.resource.query('SENS?'))
        item = [item for item in SR830.Sensitivity
                        if item.value == val][0]
        self.set_trait('sensitivity',item)
        return self.sensitivity

    def setReserveMode(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('RMOD %d' % val.value)
        self.set_trait('reserveMode',val)

    def getReserveMode(self):
        val = int(self.resource.query('RMOD?'))
        item = [item for item in SR830.ReserveMode
                           if item.value == val][0]
        self.set_trait('reserveMode', item)
        return self.reserveMode

    def setLowPassFilterSlope(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('OFSL %d' % val.value)
        self.set_trait('lowPassFilterSlope',val)

    def getLowPassFilterSlope(self):
        val = int(self.resource.query('OFSL?'))
        item = [item for item in SR830.LowPassFilterSlope
                    if item.value == val][0]
        self.set_trait('lowPassFilterSlope',item)
        return self.lowPassFilterSlope

    def setSynchronousFilterStatus(self,filterStatus: bool):
        if isinstance(filterStatus,dict):
            filterStatus = filterStatus['new']
        self.resource.write('SYNC %d' % filterStatus)
        self.set_trait('synchronousFilterStatus',filterStatus)

    def getSynchronousFilterStatus(self):
        val = int(self.resource.query('SYNC?'))
        if val ==0:
            self.set_trait('synchronousFilterStatus',False)
        else:
            self.set_trait('synchronousFilterStatus',True)
        return self.synchronousFilterStatus

    def setInputConfiguration(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('ISRC %d' % val.value)
        self.set_trait('inputConfiguration',val)

    def getInputConfiguration(self):
        val = int(self.resource.query('ISRC?'))
        item = [item for item in SR830.InputConfiguration
                    if item.value == val][0]
        self.set_trait('inputConfiguration',item)
        return self.inputConfiguration

    def setInputShieldGrounding(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('IGND %d' % val.value)
        self.set_trait('inputShieldGrounding',val)

    def getInputShieldGrounding(self):
        val = int(self.resource.query('IGND?'))
        item = [item for item in SR830.InputShieldGrounding
                    if item.value == val][0]
        self.set_trait('inputShieldGrounding',item)
        return self.inputShieldGrounding

    def setInputCoupling(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('ICPL %d' % val.value)
        self.set_trait('inputCoupling',val)

    def getInputCoupling(self):
        val = int(self.resource.query('ICPL?'))
        item = [item for item in SR830.InputCoupling
                    if item.value == val][0]
        self.set_trait('inputCoupling',item)
        return self.inputCoupling

    def setNotchFilterStatus(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('ILIN %d' % val.value)
        self.set_trait('notchFilterStatus',val)

    def getNotchFilterStatus(self):
        val = int(self.resource.query('ILIN?'))
        item = [item for item in SR830.NotchFilterStatus
                    if item.value == val][0]
        self.set_trait('notchFilterStatus',item)
        return self.notchFilterStatus

    def setReferencePhase(self,val: Quantity):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('PHAS {:.5f}'.format(val.to('deg').magnitude))
        self.set_trait('referencePhase',val)

    def getReferencePhase(self):
        val = float(self.resource.query('PHAS?'))
        self.set_trait('referencePhase',Q_(val,'deg'))
        return self.referencePhase

    def setReferenceSource(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('FMOD %d' % val.value)
        self.set_trait('referenceSource',val)

    def getReferenceSource(self):
        val = int(self.resource.query('FMOD?'))
        item = [item for item in SR830.ReferenceSource
                    if item.value == val][0]
        self.set_trait('referenceSource',item)
        return self.referenceSource
    
    def setReferenceFrequency(self,val):
        if isinstance(val,dict):
            val = val['new']
        if self.referenceSource == SR830.ReferenceSource.internal:
            self.resource.write('FREQ {:.5f}'.format(val.to('Hz').magnitude))
            self.set_trait('referenceFrequency',val)
        else:
            logging.info('SR830: Reference Frequency Setting only allowed when ' +
                            'internal source is used')

    def getReferenceFrequency(self):
        val = float(self.resource.query('FREQ?'))/1000
        self.set_trait('referenceFrequency',Q_(val,'kHz'))
        return self.referenceFrequency

    def setReferenceTrigger(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('RSLP %d' % val.value)
        self.set_trait('referenceTrigger',val)

    def getReferenceTrigger(self):
        val = int(self.resource.query('RSLP?'))
        item = [item for item in SR830.ReferenceTrigger
                    if item.value == val][0]
        self.set_trait('referenceTrigger',item)
        return self.referenceTrigger

    def setDetectionHarmonic(self,val: int):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('HARM %d' % val)
        self.set_trait('detectionHarmonic',val)

    def getDetectionHarmonic(self):
        val = int(self.resource.query('HARM?'))
        self.set_trait('detectionHarmonic',val)
        return self.detectionHarmonic

    def setSineOutputAmplitude(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('SLVL {:.3f}'.format(val.to('V').magnitude))
        self.set_trait('sineOutputAmplitude',val)

    def getSineOutputAmplitude(self):
        val = float(self.resource.query('SLVL?'))
        self.set_trait('sineOutputAmplitude', Q_(val,'V'))
        return self.sineOutputAmplitude

    @action('Auto Gain')
    async def autoGain(self):
        self.resource.write('AGAN')
        #should the lockin also do a continuous status update?
        #auto function need time, so better block
        #await self._awaitCommandExecution()

    @action('Auto Phase')
    async def autoPhase(self):
        self.resource.write('APHS')

    @action('Auto Reserve')
    async def autoReserve(self):
        self.resource.write('ARSV')

    @action('Auto Offset')
    async def autoOffset(self):
        i = 1 #set offset of X to zero
        self.resource.write('AOFF %d' % i)

    @action('Clear Status')
    def clearStatus(self):
        self.resource.write('*CLS')

    @action('Update Status')
    async def statusUpdate(self):
        status = int(self.resource.query('*STB?'))

        self.set_trait('scanInProgress',
                       not bool(status & SR830.StatusBits.NoScanInProgress.value))
        self.set_trait('commandExecutionInProgress',
                       not bool(status & SR830.StatusBits.NoCommandExecutionInProgress.value))
        self.set_trait('errorOccured',
                       bool( status & SR830.StatusBits.ErrorOccured.value))
        self.set_trait('extendedBitSet',
                       bool( status & SR830.StatusBits.ExtendedStatusBitSet.value))
        self.set_trait('interfaceOutputBuffer',
                       bool( status & SR830.StatusBits.InterfaceOutputBufferNotEmpty.value))
        self.set_trait('enabledBitSet',
                       bool(status & SR830.StatusBits.AnEnabledBitHasBeenSet.value))
        self.set_trait('serviceRequest',
                       bool(status & SR830.StatusBits.ServiceRequest.value))
        
        await self.updateLiveView()
        
        if self.enabledBitSet:
            lias = int(self.resource.query('LIAS?'))
            if bool(lias & SR830.LIABits.InputorAmplitudeOverload.value):
                logging.info('SR830: Lock-in Status Report: '+ 
                        'Input or Amplifier overload is detected!')
            if bool(lias & SR830.LIABits.TimeConstantFilterOverload.value):
                logging.info('SR830: Lock-in Status Report: ' + 
                        'Time Constant filter overload detected!')
            if bool(lias & SR830.LIABits.OutputOverload.value):
                logging.info('SR830: Lock-in Status Report: '+ 
                        'Output overload detected!') 
            if bool(lias & SR830.LIABits.ReferenceUnlock.value):
                logging.info('SR830: Lock-in Status Report: '+ 
                        'Reference unlock detected!')
            if bool(lias & SR830.LIABits.DetectionRangeSwitch.value):
                logging.info('SR830: Status Report: '+ 
                        'Detection frequency switched ranges.')
            if bool(lias & SR830.LIABits.ImplicitTimeConstantChange.value):
                logging.info('SR830: Status report-'+ 
                        'Time constant is changed indirectly, either by ' +
                        'changing frequency range, dynamic reserve, filter' +
                        'slope or expand.')
            if bool(lias & SR830.LIABits.DataStorageTriggeredExternally.value):
                logging.info('SR830: Status Report: '+ 
                        'Data storage is triggered')

        if self.errorOccured:
            error = int(self.resource.query('ERRS?'))
            if bool(error & SR830.ErrorBits.BackupError.value):
                logging.info('SR830: Lock in Error Report: ' + 
                        'Battery backup has failed after Power up')
            if bool(error & SR830.ErrorBits.RAMError.value):
                logging.info('SR830: Lock in Error Report: '+
                        'RAM Memory test found an error.')
            if bool(error & SR830.ErrorBits.ROMError.value):
                logging.info('SR830: Lock in Error Report: ' +
                        'ROM Memory test found an error.')
            if bool(error & SR830.ErrorBits.GPIBError.value):
                logging.info('SR830: Lock in Error Report: ' +
                        'GPIB fast data transfer mode aborted.')
            if bool(error & SR830.ErrorBits.DSPError.value):
                logging.info('SR830: Lock in Error Report: ' +
                        'DSP test found an error.')
            if bool(error & SR830.ErrorBits.MathError.value):
                logging.info('SR830: Lock in Error Report: ' +
                        'Internal math error occured.')

        if self.extendedBitSet:
            event = int(self.resource.query('*ESR?'))
            if bool(event & SR830.StandardEventBits.InputQueueOverflow.value):
                logging.info('SR830: Lock In Standard Event Report: '+ 
                        'Input queue overflow (too many commands' +
                        ' received at once, queues cleared).')
            if bool(event & SR830.StandardEventBits.OutputQueueOverflow.value):
                logging.info('SR830: Lock In Standard Event Report: '+ 
                        'Output queue overflow (too many respons' +
                        'es waiting to be transmitted, queues cleared).')
            if bool(event & SR830.StandardEventBits.ParameterOutOfRange.value):
                logging.info('SR830: Lock In Standard Event Report: '+ 
                        'Command can not execute correctly '+
                        'or a parameter is out of range.')
            if bool(event & SR830.StandardEventBits.IllegalCommand.value):
                logging.info('SR830: Lock In Standard Event Report: '+ 
                        'Illegal command received')
            if bool(event & SR830.StandardEventBits.KeyPressed.value):
                logging.info('SR830: Lock In Standard Event Report: '+ 
                        'Any key press or knob rotation!')
            if bool(event & SR830.StandardEventBits.PowerOn.value):
                logging.info('SR830: Lock In Standard Event Report: '+ 
                        'Set by Power on')
    
    @threaded_async
    def updateLiveView(self):
        
        vals = self.resource.query('SNAP?1,2,3,4,9')
        vals = list(map(float,vals.split(',')))
        
        self.set_trait('liveViewValueX',Q_(vals[0],'V').to('pV'))
        self.set_trait('liveViewValueY',Q_(vals[1],'V').to('pV'))
        self.set_trait('liveViewValueR',Q_(vals[2],'V').to('pV'))
        self.set_trait('liveViewValueTheta',Q_(vals[3],'deg'))
        self.set_trait('liveViewValueRefF',Q_(vals[4],'Hz').to('kHz'))
        
        if self.liveViewValueX > self.liveViewMaxValue:
            self.set_trait('liveViewMaxValue',self.liveViewValueX)
        if self.liveViewValueX < self.liveViewMinValue:
            self.set_trait('liveViewMinValue',self.liveViewValueX)

    @action('reset values', group='Live View')
    def resetLiveViewValues(self):
        self.set_trait('liveViewMaxValue',self.liveViewValueX)
        self.set_trait('liveViewMinValue',self.liveViewValueX)
        
    async def contLiveViewUpdate(self):
        while True:
            await asyncio.sleep(0.33)
            await self.updateLiveView()
            
    @action('start update',group='Live View')
    async def startLiveViewUpdate(self):
        self._liveViewFuture = ensure_weakly_binding_future(self.contLiveViewUpdate)
        logging.info('SR830: Live View Enabled')
        
    @action('stop update', group='Live View')
    def stopLiveViewUpdate(self):
        self._liveViewFuture.cancel()
        logging.info('SR830: Live View Disabled')
        
    @traitlets.observe('saveSettings')
    def saveSettingsToLockin(self,val):
        if isinstance(val,dict):
            val = val['new']

        self.resource.write('SSET %d' % val)

    @traitlets.observe('loadSettings')
    def loadSettingsFromLockin(self,val):
        if isinstance(val,dict):
            val = val['new']
        self.resource.write('RSET %d' % val)

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
            self._dataSetReady(dataSet)
            return dataSet

        elif (self.samplingMode == SR830.SamplingMode.Buffered):
            data = np.array(await self.readDataBuffer())
            dataSet = DataSet(Q_(data), [Q_(np.arange(0, len(data)))])
            self._dataSetReady(dataSet)
            return dataSet
