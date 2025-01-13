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
import asyncio
import enum
import logging
import os
import time
from threading import Lock
import pyvisa
import traitlets
from asyncioext import ensure_weakly_binding_future, threaded_async
from common import ComponentBase, ureg, Q_, action

logging.basicConfig(level=logging.INFO)

error_map = {b"1": "Error in sent number",
             b"2": "Endswitch triggered. Reinitialize controller",
             b"3": "Access to undefined axis",
             b"4": "Axis number not set (not initialized)",
             b"5": "Syntax error",
             b"6": "End of memory",
             b"7": "Bad number of parameters",
             b"8": "Cannot save command: incorrect command",
             b"9": "Device error 9. Reinitialize controller",
             b"A": 0, "B": 0, "C": 0,
             b"D": "Velocity out of bounds",
             b"E": 0,
             b"F": "User stop",
             b"G": "Bad data field",
             b"H": "Cover error",
             b"R": "Reference error",
             b"=": 0
             }

class Controller(ComponentBase):
    class AxisCount(enum.Enum):
        X = 1
        X_Y = 3
        X_Y_Z = 7
        A = 8  # ACHTUNG: Die A-Achse muss immer separat initialisiert werden. (??)

    axis_idx_map = {1:0, 2:1, 4:2, 8:3}

    DEFAULT_TIMEOUT = 1000
    MOVEMENT_TIMEOUT = 100000
    STATUS_UPDATE_RATE = 3

    # Instrument Info Traitlets
    controlUnitInfo = traitlets.Unicode(read_only=True, name="Control Unit Info", group="Instrument Info")
    has_error = False

    #Parameters
    parameterTraits = ["referenceSpeed", "acceleration", "startStopFrequency", "axisDirection", "referenceDirection"]

    def __init__(self, comport, baudRate=19200):
        super().__init__()

        self._lock = Lock()
        self.comport = comport

        if os.name == 'posix':
            rm = pyvisa.ResourceManager('@py')
            self.comport = "ASRL" + self.comport + "::INSTR"
        elif os.name == 'nt':
            rm = pyvisa.ResourceManager()

        try:
            self.resource = rm.open_resource(self.comport)
        except pyvisa.errors.VisaIOError:
            raise Exception('Failed to open ISEL_iMC_P stage at comport: ' + self.comport)


        self.resource.read_termination = ''
        self.resource.write_termination = chr(13)  # CR
        self.resource.baud_rate = baudRate
        self.resource.timeout = self.DEFAULT_TIMEOUT

        self.registered_axes = []
        self.axis_cnt = None

    def register_axis(self, axis):
        for ax in self.registered_axes:
            if ax.axis == axis.axis:
                raise Exception(f'Axis already registered at {axis.axis}')
        self.registered_axes.append(axis)

    async def __aenter__(self):
        await super().__aenter__()
        await self.initializeControlUnit()
        # await self.getControlUnitInfo()
        return self

    async def initializeControlUnit(self):
        """
        Initialisation, setting number of axes.
        """
        if not self.registered_axes:
            raise Exception('No registered axes. Initialization failed')

        if len(self.registered_axes) == 1:
            self.axis_cnt = self.AxisCount.X
        elif len(self.registered_axes) == 2:
            self.axis_cnt = self.AxisCount.X_Y
        elif len(self.registered_axes) == 3:
            self.axis_cnt = self.AxisCount.X_Y_Z
        elif len(self.registered_axes) == 4:
            self.axis_cnt = self.AxisCount.A
        else:
            raise Exception('Invalid number of axes registerered')

        await self.write(f"@0{self.axis_cnt.value}")


    async def getControlUnitInfo(self):
        """
        Queries info of the control unit.
        """

        info = await self.query("@0V")
        info = info[0]
        self.set_trait("controlUnitInfo", info[0:-2])

    @threaded_async
    def write(self, command, lock=True):
        """
        Sends a command to the device.

        Parameters
        ----------
        command : str
            The command to send to the device.
        lock : bool
            Use the lock if true. Prevents simultaneous access on the instrument.
        """

        logging.info('{}: {}'.format(self, command))
        if lock:
            with self._lock:
                self.resource.write(command)
                self.readAllBytes()
        else:
            self.resource.write(command)
            self.readAllBytes()

    @threaded_async
    def read(self):
        """
        Reads the current content of the receive buffer

        Returns
        -------
        result : coroutine
            The read content of the receive buffer.
        """

        with self._lock:
            readBytes = self.readAllBytes()
            if len(readBytes) > 0:
                result = b''.join(readBytes).decode("utf-8")
                logging.warning("read(): result: " + result)
                return result

    def readAllBytes(self):
        """
        Reads all bytes from the receive buffer.

        Returns
        -------
        allBytes : list
            All bytes read from the receive buffer.
        """
        time.sleep(0.05)  # self.resource.bytes_in_buffer gives wrong result if called right after write
        allBytes = []
        try:
            allBytes.append(self.resource.read_bytes(1))
        except:
            logging.warning("readAllBytes: no bytes in buffer")
            return []

        while self.resource.bytes_in_buffer > 0:
            allBytes.append(self.resource.read_bytes(1))

        if allBytes[0] in error_map:
            logging.warning(error_map[allBytes[0]])
            self.has_error = True  # TODO not correctly implemented
            return []
        else:
            self.has_error = False

        return allBytes[1:]

    @threaded_async
    def query(self, command, timeout=None, en_log=True):
        """
        Sends a command to the device and reads the answer.

        Parameters
        ----------
        command : str
            The command to send to the device.
        timeout : int
            Custom timeout in ms.

        Returns
        -------
        coroutine
            A list of answer strings from the device.
        """

        with self._lock:
            # remove parameter placeholders from command
            paramIndex = command.find(" {}")
            if paramIndex != -1:
                command = command[:paramIndex]

            if en_log:
                logging.info('ISEL_iMC_P query: ' + str(command))
            # logging.info('{}: {}'.format(self, command))

            if timeout is not None:
                prevTimeout = self.resource.timeout
                self.resource.timeout = timeout

            self.resource.write(command)
            answerBytes = self.readAllBytes()
            answerString = b''.join(answerBytes).decode("utf-8")

            if en_log:
                logging.info('ISEL_iMC_P answer: ' + answerString)

            if timeout is not None:
                self.resource.timeout = prevTimeout

            result = []
            for s in str.split(answerString, ','):
                result.append(s)

            return result

    def setParameterOnDevice(self, change):
        """
        Sets parameter on the device.

        This is the function that is called by all traits that get observed. Tries to update the changed attribute on
        the device by sending the corresponding command.

        Parameters
        ----------
        change : list
            change object of the observed trait.
        """

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
        elif isinstance(value, bool):
            value = 1 if value else 0

        commandString = str()
        paramIndex = command.find("{}")
        if paramIndex == -1:
            commandString = command + '{}'.format(value)
        elif command.find("{},{}") != -1:
            commandString = command.format(value[0], value[1])
        elif paramIndex != -1:
            commandString = command.format(value)

        asyncio.ensure_future(self.write(commandString))

    @action("Break")
    async def softwareBreak(self):
        self.resource.write_raw(bytes([255]))
        await self.read()

    @action("Software Reset")
    async def softwareReset(self):
        self.connection.write_raw(bytes([254]))
        await self.read()

    @action("Load Parameters from Flash", group="Parameters")
    async def loadParametersFromFlash(self):
        await self.write("@0IL")

    @action("Save Parameters to Flash", group="Parameters")
    async def saveParametersToFlash(self):
        await self.write("@0IW")

    @action("Load Default Parameters", group="Parameters")
    async def loadDefaultParameters(self):
        await self.write("@0IX")

    async def executeMovementCommand(self, axis, val, velocity):
        ax_cnt = len(self.registered_axes)
        positions = [str(pos) for pos in await self.getPositions()]
        positions = positions[:ax_cnt]

        empty_command = list(zip(positions, ax_cnt*[str(velocity)]))
        empty_command = [item for tup in empty_command for item in tup]
        logging.warning(empty_command)

        try:
            axis_idx = self.axis_idx_map[axis.value]
        except KeyError:
            raise Exception("Invalid axis value")

        empty_command[2*axis_idx], empty_command[2*axis_idx+1] = str(val), str(velocity)
        command = "@0M " + ",".join(empty_command)
        logging.warning(command)

        return await self.query(command, self.MOVEMENT_TIMEOUT)

    async def getPositions(self, axis=None):
        pos_query_answer = await self.query("@0P", en_log=False)
        if not pos_query_answer[0]:
            return

        position_str = pos_query_answer[0]

        if self.axis_cnt != self.AxisCount.A:
            position_str = position_str[0:6], position_str[6:12], position_str[12:18]
        else:
            position_str = position_str[0:6], position_str[6:12], position_str[12:18], position_str[18:24]
        position_str = [int(pos, 16) for pos in position_str]

        if axis is None:
            return position_str
        else:
            return position_str[self.axis_idx_map[axis.value]]

    async def referenceAxis(self, axis):
        return await self.query(f"@0R{axis.value}")

    async def setZero(self, axis):
        return await self.query(f"@0n{axis.value}")

