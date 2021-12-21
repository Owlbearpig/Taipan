"""
This file is part of Taipan.

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
from pyvisa import constants as pyvisa_consts
import asyncio
import struct
import enum
import traitlets
import logging


class SR7230(DataSource):
    """
    Implementation of the Lock-In SR7230 as a DataSource

    This class implements the Lock-In Amplifier SR7230 as a DataSource using PyVisa for the connection to the device.
    Most attributes of this class represent attributes of the device. Refer to the official manual of the SR7230 for
    more details.
    """


    class SamplingMode(enum.Enum):
        SingleShot = 0
        Buffered = 1

    # Signal Channel

    class InputMode(enum.Enum):
        VoltageInputMode = 0
        CurrentModeHighBandwidth = 1
        CurrentModeLowNoise = 2

    class VoltageInputMode(enum.Enum):
        BothInputsGrounded = 0
        AInputOnly = 1
        BInputOnly = 2
        ABDifferentialMode = 3

    class InputConnectorShieldControl(enum.Enum):
        Ground = 0
        Float = 1

    class InputDevice(enum.Enum):
        Bipolar = 0
        FET = 1

    class InputCoupling(enum.Enum):
        AC = 0
        DC = 1

    class SensitivityIMode0(enum.Enum):
        Sens_10nV = 3
        Sens_20nV = 4
        Sens_50nV = 5
        Sens_100nV = 6
        Sens_200nV = 7
        Sens_500nV = 8
        Sens_1muV = 9
        Sens_2muV = 10
        Sens_5muV = 11
        Sens_10muV = 12
        Sens_20muV = 13
        Sens_50muV = 14
        Sens_100muV = 15
        Sens_200muV = 16
        Sens_500muV = 17
        Sens_1mV = 18
        Sens_2mV = 19
        Sens_5mV = 20
        Sens_10mV = 21
        Sens_20mV = 22
        Sens_50mV = 23
        Sens_100mV = 24
        Sens_200mV = 25
        Sens_500mV = 26
        Sens_1V = 27

    class ACGain(enum.Enum):
        Gain_0dB = 0
        Gain_6dB = 1
        Gain_12dB = 2
        Gain_18dB = 3
        Gain_24dB = 4
        Gain_30dB = 5
        Gain_36dB = 6
        Gain_42dB = 7
        Gain_48dB = 8
        Gain_54dB = 9
        Gain_60dB = 10
        Gain_66dB = 11
        Gain_72dB = 12
        Gain_78dB = 13
        Gain_84dB = 14
        Gain_90dB = 15

    class ACGainControl(enum.Enum):
        Manual = 0
        Automatic = 1

    class NotchFilter(enum.Enum):
        Off = [0, 1]
        NotchFilter_50Hz = [1, 0]
        NotchFilter_60Hz = [1, 1]
        NotchFilter_100Hz = [2, 0]
        NotchFilter_120Hz = [2, 1]
        NotchFilter_50Hz_100Hz = [3, 0]
        NotchFilter_60Hz_120Hz = [3, 1]

    class NotchFilters(enum.Enum):
        Off = 0
        NotchFilter50or60Hz = 1
        NotchFilter100or120Hz = 2
        Both = 3

    class NotchFilterCenterFrequencies(enum.Enum):
        Freq_60_120_Hz = 0
        Freq_50_100_Hz = 1

    # Reference Channel

    class ReferenceMode(enum.Enum):
        SingleReference = 0
        DualHarmonic = 1
        DualReference = 2

    class ReferenceSource(enum.Enum):
        Internal = 0
        ExternalTTL = 1
        ExternalAnalog = 2

    class ReferenceChannelSelection(enum.Enum):
        CH1_Internal_CH2_External = 0
        CH2_Internal_CH1_External = 1

    class ReferenceMonitorControl(enum.Enum):
        TrigOutByCurveBuffer = 0
        TrigOutTTLAtReferenceFreq = 1

    # Signal Channel Output Filters

    class FilterTimeConstant(enum.Enum):
        TimeConstant_10mus = 0
        TimeConstant_20mus = 1
        TimeConstant_50mus = 2
        TimeConstant_100mus = 3
        TimeConstant_200mus = 4
        TimeConstant_500mus = 5
        TimeConstant_1ms = 6
        TimeConstant_2ms = 7
        TimeConstant_5ms = 8
        TimeConstant_10ms = 9
        TimeConstant_20ms = 10
        TimeConstant_50ms = 11
        TimeConstant_100ms = 12
        TimeConstant_200ms = 13
        TimeConstant_500ms = 14
        TimeConstant_1s = 15
        TimeConstant_2s = 16
        TimeConstant_5s = 17
        TimeConstant_10s = 18
        TimeConstant_20s = 19
        TimeConstant_50s = 20
        TimeConstant_100s = 21
        TimeConstant_200s = 22
        TimeConstant_500s = 23
        TimeConstant_1ks = 24
        TimeConstant_2ks = 25
        TimeConstant_5ks = 26
        TimeConstant_10ks = 27
        TimeConstant_20ks = 28
        TimeConstant_50ks = 29
        TimeConstant_100ks = 30

    class LowPassFilterSlope(enum.Enum):
        FilterSlope_6db_octave = 0
        FilterSlope_12db_octave = 1
        FilterSlope_18db_octave = 2
        FilterSlope_24db_octave = 3

    # Curve Buffer

    class CurveBufferMode(enum.Enum):
        Standard = 0
        Fast = 1

    class CurveBufferTriggerOutput(enum.Enum):
        PerCurve = 0
        PerPoint = 1

    class CurveBufferTriggerOutputPolarity(enum.Enum):
        RisingEdge = 0
        FallingEdge = 1

    class TakeDataMode(enum.Enum):
        TakeData = 0
        TakeDataTriggered = 1
        TakeDataContinuously = 2

    class TakeDataTriggeredTriggerMode(enum.Enum):
        Start_ExtRising_Sample_NA_Stop_LEN = 0
        Start_Cmd_Sample_ExtRising_Stop_LEN = 1
        Start_ExtFalling_Sample_NA_Stop_LEN = 2
        Start_Cmd_Sample_ExtFalling_Stop_LEN = 3
        Start_ExtRising_Sample_NA_Stop_Cmd = 4
        Start_Cmd_Sample_ExtRising_Stop_Cmd = 5
        Start_ExtFalling_Sample_NA_Stop_Cmd = 6
        Start_Cmd_Sample_ExtFalling_Stop_Cmd = 7
        Start_ExtRising_Sample_NA_Stop_ExtFalling = 8
        Start_ExtFalling_Sample_NA_Stop_ExtRising = 9

    class StatusBits(enum.Enum):
        CommandComplete = 0x1
        InvalidCommand = 0x2
        CommandParameterError = 0x4
        ReferenceUnlock = 0x8
        OutputOverload = 0x10
        NewADCValues = 0x20
        InputOverload = 0x40
        DataAvailable = 0x80

    class OverloadBits(enum.Enum):
        X = 0x1
        Y = 0x2
        X2 = 0x4
        Y2 = 0x8
        CH1 = 0x10
        CH2 = 0x20
        CH3 = 0x40
        CH4 = 0x80

    class CurveAcquisitionStatusInts(enum.Enum):
        NoCurveActivity = 0
        AcquisitionTD = 1
        AcquisitionTDC = 2
        AcquisitionHaltedTD = 5
        AcquisitionHaltedTDC = 6

    statusMessages = {
        'overload': {0x1: 'X channel output overload',
                     0x2: 'Y channel output overload',
                     0x4: 'X2 channel output overload',
                     0x8: 'Y2 channel output overload',
                     0x10: 'CH1 channel output overload',
                     0x20: 'CH2 channel output overload',
                     0x40: 'CH3 channel output overload',
                     0x80: 'CH4 channel output overload'}
    }

    STATUS_UPDATE_RATE = 5

    # Instrument Info Traitlets

    identification = traitlets.Unicode(read_only=True, name="Identification", group="Instrument Info")
    instrumentName = traitlets.Unicode(name="Instrument Name", group="Instrument Info", command="NAME")
    firmwareVersion = traitlets.Unicode(read_only=True, name="Firmware Version", group="Instrument Info")

    # General Traitlets Traitlets

    samplingMode = traitlets.Enum(SamplingMode, SamplingMode.Buffered).tag(name="Sampling mode")

    # Signal Channel Traitlets

    inputMode = traitlets.Enum(InputMode, default_value=InputMode.VoltageInputMode).tag(group="Signal Channel",
                                                                                        command="IMODE")
    voltageInputMode = traitlets.Enum(VoltageInputMode).tag(group="Signal Channel", command="VMODE")
    inputConnectorShieldControl = traitlets.Enum(InputConnectorShieldControl,
                                                 default_value=InputConnectorShieldControl.Ground) \
        .tag(group="Signal Channel", command="FLOAT")
    inputDevice = traitlets.Enum(InputDevice, default_value=InputDevice.FET).tag(group="Signal Channel",
                                                                                 command="FET")
    inputCoupling = traitlets.Enum(InputCoupling, default_value=InputCoupling.AC).tag(group="Signal Channel",
                                                                                      command="DCCOUPLE")
    sensitivity = traitlets.Enum(SensitivityIMode0, default_value=SensitivityIMode0.Sens_200mV).tag(
        group="Signal Channel", command="SEN")
    acGain = traitlets.Enum(ACGain, default_value=ACGain.Gain_0dB).tag(group="Signal Channel", command="ACGAIN")
    acAutomaticGainControl = traitlets.Bool(default_value=False, group="Signal Channel", command="AUTOMATIC")
    notchFilter = traitlets.Enum(NotchFilter, default_value=NotchFilter.Off, group="Signal Channel",
                                 command="LF {} {}")

    # Reference Channel Traitlets

    referenceMode = traitlets.Enum(ReferenceMode, default_value=ReferenceMode.SingleReference,
                                   group="Reference Channel", command="REFMODE")
    referenceSource = traitlets.Enum(ReferenceSource, default_value=ReferenceSource.Internal, group="Reference Channel",
                                     command="IE")
    referenceChannelSelection = traitlets.Enum(ReferenceChannelSelection, group="Reference Channel", command="INT")
    referenceHarmonicMode = traitlets.Int(default_value=1, min=1, max=127, group="Reference Channel", command="REFN")
    referenceMonitorControl = traitlets.Enum(ReferenceMonitorControl, group="Reference Channel", command="REFMON")
    referencePhase = Quantity(default_value=Q_(0, "mdeg"), min=Q_(-360000, "mdeg"), max=Q_(360000, "mdeg"))
    referencePhase.tag(group="Reference Channel", command="REFP")
    referenceFrequencyMeter = Quantity(default_value=Q_(0, 'mHz'), read_only=True)
    referenceFrequencyMeter.tag(group="Reference Channel", command="FRQ")
    enterVirtualReferenceMode = traitlets.Bool(group="Reference Channel", command="VRLOCK")

    # Signal Channel Output Filters

    noiseMode = traitlets.Bool(default_value=False, read_only=True, group="Signal Channel Output Filters",
                               command="NOISEMODE")
    fastMode = traitlets.Bool(default_value=True, read_only=False, group="Signal Channel Output Filters",
                              command="FASTMODE")
    filterTimeConstant = traitlets.Enum(FilterTimeConstant, group="Signal Channel Output Filters", command="TC")
    synchronousTimeConstantControl = traitlets.Bool(default_value=True, group="Signal Channel Output Filters",
                                                    command="SYNC")
    lowPassFilterSlope = traitlets.Enum(LowPassFilterSlope, default_value=LowPassFilterSlope.FilterSlope_12db_octave,
                                        group="Signal Channel Output Filters", command="SLOPE")

    # Data Curve Buffer Traitlets

    bufferMode = traitlets.Enum(CurveBufferMode, default_value=CurveBufferMode.Standard, read_only=True,
                                command="CMODE", group="Data Curve Buffer")
    bufferTriggerOutput = traitlets.Enum(CurveBufferTriggerOutput, command="TRIGOUT", group="Data Curve Buffer")
    bufferTriggerOutputPolarity = traitlets.Enum(CurveBufferTriggerOutputPolarity, command="TRIGOUTPOL",
                                                 group="Data Curve Buffer")
    storageTimeInterval = traitlets.Int(default_value=10).tag(name="Storage Time Interval", command="STR",
                                                              group="Data Curve Buffer")
    bufferLength = traitlets.Int(default_value=100000).tag(name="Buffer Length", command="LEN",
                                                           group="Data Curve Buffer")
    takeDataMode = traitlets.Enum(TakeDataMode, TakeDataMode.TakeData).tag(name="Take Data Mode",
                                                                           group="Data Curve Buffer")
    takeDataTriggeredTriggerMode = traitlets.Enum(
        TakeDataTriggeredTriggerMode, default_value=TakeDataTriggeredTriggerMode.Start_ExtRising_Sample_NA_Stop_LEN,
        group="Data Curve Buffer")
    curveAcquisitionInProgressTD = traitlets.Bool(default_value=False, read_only=True).tag(
        name="Acquisition in Progress by TD",
        group='Data Curve Buffer')
    curveAcquisitionInProgressTDC = traitlets.Bool(default_value=False, read_only=True).tag(
        name="Continuous Acquisition in Progress",
        group='Data Curve Buffer')
    curveAcquisitionHaltedTD = traitlets.Bool(default_value=False, read_only=True).tag(
        name="Acquisition by TD Halted",
        group='Data Curve Buffer')
    curveAcquisitionHaltedTDC = traitlets.Bool(default_value=False, read_only=True).tag(
        name="Continuous Acquisition by TD Halted",
        group='Data Curve Buffer')
    pointsAcquired = traitlets.Int(default_value=0, read_only=True).tag(name="Points Acquired",
                                                                        group='Data Curve Buffer')

    # Status Traitlets

    curveAcquisitionInProgress = traitlets.Bool(default_value=False, read_only=True).tag(
        name="Curve Acquisition in Progress",
        group='Status')
    commandComplete = traitlets.Bool(default_value=False, read_only=True).tag(name="Command Complete", group="Status")
    invalidCommand = traitlets.Bool(default_value=False, read_only=True).tag(name="Invalid Command", group="Status")
    commandParameterError = traitlets.Bool(default_value=False, read_only=True).tag(name="Command Parameter Error",
                                                                                    group="Status")
    referenceUnlock = traitlets.Bool(default_value=False, read_only=True).tag(name="Reference Unlock", group="Status")
    outputOverload = traitlets.Bool(default_value=False, read_only=True).tag(name="Output Overload", group="Status")
    newADCValues = traitlets.Bool(default_value=False, read_only=True).tag(name="New ADC Values", group="Status")
    inputOverload = traitlets.Bool(default_value=False, read_only=True).tag(name="Input Overload", group="Status")
    dataAvailable = traitlets.Bool(default_value=False, read_only=True).tag(name="Data Available", group="Status")

    def __init__(self, resource, ethernet=False):
        """
        Parameters
        ----------
        resource : Resource
            PyVisa Resource object of the connected device.
        ethernet : bool
            Indicates if the connection to the device is an ethernet connection.
        """

        super().__init__(objectName=None, loop=None)
        self.resource = resource
        self.ethernet = ethernet
        self.resource.timeout = 1000
        self.resource.set_visa_attribute(pyvisa_consts.VI_ATTR_SUPPRESS_END_EN, pyvisa_consts.VI_FALSE)

        if ethernet:
            self.resource.read_termination = chr(0)
        else:
            self.resource.read_termination = ''
        self.resource.write_termination = chr(0)

        self.observe(self.setParameter, traitlets.All)

        self._traitChangesDueToStatusUpdate = True
        self._lock = Lock()

        self._statusUpdateFuture = ensure_weakly_binding_future(self.contStatusUpdate)



    async def __aenter__(self):
        await super().__aenter__()
        self.set_trait("identification", (await self.query("ID"))[0])
        self.set_trait("instrumentName", (await self.query("NAME"))[0])
        self.set_trait("firmwareVersion", (await self.query("VER"))[0])
        await self.readAllParameters()
        await self.statusUpdate()
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._statusUpdateFuture.cancel()

    @threaded_async
    def query(self, command):
        """
        Sends a command to the device and reads the answer.

        Parameters
        ----------
        command : str
            The command to send to the device.

        Returns
        -------
        list
            a list of answer strings from the device.
        """

        with self._lock:
            # remove parameter placeholders from command
            paramIndex = command.find(" {}")
            if paramIndex != -1:
                command = command[:paramIndex]

            print('SR7230: query ' + str(command))
            logging.info('{}: {}'.format(self, command))

            answer = self.resource.query(command)

            if self.ethernet:
                self.resource.read_raw()
            else:
                end = answer.find(chr(0))
                answer = answer[:end]

            print('SR7230: answer: ' + answer)

            result = []
            for s in str.split(answer, ','):
                result.append(s)

            return result

    @threaded_async
    def write(self, command, lock=True):
        """
        Sends a command to the device.

        Parameters
        ----------
        command : str
            The command to send to the device.
        """

        logging.info('{}: {}'.format(self, command))
        if lock:
            with self._lock:
                ret = self.resource.query(command)
                if self.ethernet:
                    self.resource.read_raw()
                return ret
        else:
            ret = self.resource.query(command)
            if self.ethernet:
                self.resource.read_raw()
            return ret

    async def getCurveAcquisitionStatusMonitor(self):
        """
        Gets the current curve acquisition status.

        Returns
        -------
        list
            a list of the curve acquisition status monitor values.
        """

        answer = await self.query('M')
        # if answer[-1] == '\n':
        #     answer = answer[:-1]
        # result = []
        # for s in str.split(answer, ','):
        #     result.append(int(s))

        return answer

    async def getNumberOfPointsAcquired(self):
        """
        Gets the current number of acquired points from the device.

        Returns
        -------
        int
            the number of points acquired.
        """

        result = await self.getCurveAcquisitionStatusMonitor()
        return result[3]

    @action("Start")
    async def start(self):
        print('start sr7230')
        await self.write('NC')  # new curve
        await self.write('CBD 1')  # select channel x
        if self.takeDataMode == self.TakeDataMode.TakeData:
            await self.write('TD')
        elif self.takeDataMode == self.TakeDataMode.TakeDataContinuously:
            await self.write('TDC 0')
        elif self.takeDataMode == self.TakeDataMode.TakeDataTriggered:
            await self.write("TDT {}".format(self.takeDataTriggeredTriggerMode))

        await self.statusUpdate()

    @action("Stop")
    async def stop(self):
        print('stop sr7230')
        await self.write('HC')

    @action("Clear Buffer", group="Data Curve Buffer")
    async def clear(self):
        """
        Clears the buffer of the device.
        """

        await self.write("NC")

    async def readAllParameters(self):
        """
        Reads all parameters from the device and updates the attributes of this class accordingly.
        """

        self._traitChangesDueToStatusUpdate = True

        for name, trait in self.traits().items():
            command = trait.metadata.get('command')

            if command is None:
                continue
            else:
                answer = await self.query(command)

            if len(answer) == 1:
                result = answer[0]
            else:
                result = answer

            if isinstance(trait, traitlets.Enum):
                if len(answer) == 1:
                    val = int(result)
                    val = [item for item in trait.values if item.value == val][0]
                else:
                    res = []
                    for i in answer:
                        ival = int(i)
                        res.append(ival)
                    val = [item for item in trait.values if item.value == res][0]
            elif isinstance(trait, Quantity):
                val = Q_(float(result), trait.default_value.units)
            elif isinstance(trait, traitlets.Int):
                val = int(result)
            elif isinstance(trait, traitlets.Bool):
                result_int = 0
                try:
                    result_int = int(result)
                except ValueError:
                    print('Failed to read answer from ' + command + " answer was " + str(result))
                    logging.info('Failed to read answer from ' + command + " answer was " + str(result))
                    
                val = True if result_int == 1 else False
            else:
                val = result

            self.set_trait(name, val)

        self._traitChangesDueToStatusUpdate = False
        logging.info('SR7230: Lockin-Parameter read')

    def setParameter(self, change):
        """
        Sets parameter on the device.

        This is the function that is called by all traits that get observed. Tries to update the changed attribute on
        the device by sending the corresponding command.

        Parameters
        ----------
        change : list
            change object of the observed trait.
        """

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
            if 'REFP' in command:
                value = int(value.magnitude)
            else:
                value = value.magnitude
        elif isinstance(value, bool):
            value = 1 if value else 0

        commandString = str()
        paramIndex = command.find(" {}")
        if paramIndex == -1:
            commandString = command + ' {}'.format(value)
        elif command.find("{} {}") != -1:
            commandString = command.format(value[0], value[1])
        elif paramIndex != -1:
            commandString = command.format(value)

        asyncio.ensure_future(self.write(commandString))

    # Auto Functions
    @action('Readout Settings', group='Auto Functions')
    def readSettings(self):
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Sensitivity', group='Auto Functions')
    def autoSensitivity(self):
        asyncio.ensure_future(self.write('AS'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Measure Operation', group='Auto Functions')
    def autoMeasureOperation(self):
        asyncio.ensure_future(self.write('ASM'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Phase', group='Auto Functions')
    def autoPhase(self):
        asyncio.ensure_future(self.write('AQN'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Auto Offset', group='Auto Functions')
    def autoOffset(self):
        asyncio.ensure_future(self.write('AXO'))
        asyncio.ensure_future(self.readAllParameters())

    @action('Update Gain and Phase Correction Parameters', group='Reference Channel')
    def systemLockControl(self):
        asyncio.ensure_future(self.write('LOCK'))
        asyncio.ensure_future(self.readAllParameters())

    async def contStatusUpdate(self):
        """
        Requests a status update every STATUS_UPDATE_RATE seconds.
        """

        while True:
            await asyncio.sleep(self.STATUS_UPDATE_RATE)
            await self.statusUpdate()

    async def statusUpdate(self):
        """
        Performs a status update and updates the class attributes according to answers from the device.
        """

        curveAcquisitionStatusMonitor = await self.getCurveAcquisitionStatusMonitor()
        curveAcquisitionStatus = int(curveAcquisitionStatusMonitor[0])
        status = int(curveAcquisitionStatusMonitor[2])

        self.set_trait("curveAcquisitionInProgressTD",
                       curveAcquisitionStatus == SR7230.CurveAcquisitionStatusInts.AcquisitionTD.value)
        self.set_trait("curveAcquisitionInProgressTDC",
                       curveAcquisitionStatus == SR7230.CurveAcquisitionStatusInts.AcquisitionTDC.value)
        self.set_trait("curveAcquisitionHaltedTD",
                       curveAcquisitionStatus == SR7230.CurveAcquisitionStatusInts.AcquisitionHaltedTD.value)
        self.set_trait("curveAcquisitionHaltedTDC",
                       curveAcquisitionStatus == SR7230.CurveAcquisitionStatusInts.AcquisitionHaltedTDC.value)
        self.set_trait("pointsAcquired", int(curveAcquisitionStatusMonitor[3]))

        self.set_trait("curveAcquisitionInProgress",
                       curveAcquisitionStatus != SR7230.CurveAcquisitionStatusInts.NoCurveActivity.value)
        self.set_trait("commandComplete", bool(status & SR7230.StatusBits.CommandComplete.value))
        self.set_trait("invalidCommand", bool(status & SR7230.StatusBits.InvalidCommand.value))
        self.set_trait("commandParameterError", bool(status & SR7230.StatusBits.CommandParameterError.value))
        self.set_trait("referenceUnlock", bool(status & SR7230.StatusBits.ReferenceUnlock.value))
        self.set_trait("outputOverload", bool(status & SR7230.StatusBits.OutputOverload.value))
        self.set_trait("newADCValues", bool(status & SR7230.StatusBits.NewADCValues.value))
        self.set_trait("inputOverload", bool(status & SR7230.StatusBits.InputOverload.value))
        self.set_trait("dataAvailable", bool(status & SR7230.StatusBits.DataAvailable.value))

        if self.outputOverload:
            overloadByte = await self.query("N")
            logging.info(SR7230.statusMessages['overload'][overloadByte])

    async def readCurrentOutput(self, channel='X'):
        """
        Reads the current output of a channel from the device.

        Parameters
        ----------
        channel : str
            the channel to read from.

        Returns
        -------
        float
            the current output.
        """

        return float(await self.query(channel))

    async def readDataBuffer(self):
        """
        Reads the data buffer of the device

        Returns
        -------
        list
            a list of the read data points from the device's data buffer.
        """

        numberOfPoints = await self.getNumberOfPointsAcquired()
        print('number of points: ' + str(numberOfPoints))
        if numberOfPoints == 0:
            return []
        data = await self.query('DC 0')
        data = data[0]

        result = []
        for s in str.split(data, '\n'):
            try:
                dataPoint = float(s)
                result.append(dataPoint)
            except ValueError:
                pass

        return result

    async def readDataSet(self):
        if self.samplingMode == SR7230.SamplingMode.SingleShot:
            data = np.array(await self.readCurrentOutput())
            dataSet = DataSet(Q_(data), [])
            self._dataSetReady(dataSet)
            return dataSet
        elif self.samplingMode == SR7230.SamplingMode.Buffered:
            data = await self.readDataBuffer()
            data = np.array(data)
            dataSet = DataSet(Q_(data), [Q_(np.arange(0, len(data)))])
            self._dataSetReady(dataSet)
            return dataSet
