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


class Connection(ComponentBase):
    class AxisCount(enum.Enum):
        X = 1
        X_Y = 3
        X_Y_Z = 7
        A = 8  # ACHTUNG: Die A-Achse muss immer separat initialisiert werden. (??)

    class AxisDirection(enum.Enum):
        """
        Bit0 --> X-Achse
        Bit1 --> Y-Achse
        00 --> Beide Normal
        11--> Beide Invertiert
        weitere Möglichkeiten 01, 10
        """
        Normal = 00
        Inverse = 11

    DEFAULT_TIMEOUT = 1000
    MOVEMENT_TIMEOUT = 100000
    STATUS_UPDATE_RATE = 3

    # Instrument Info Traitlets
    controlUnitInfo = traitlets.Unicode(read_only=True, name="Control Unit Info", group="Instrument Info")

    #Parameters
    axisDirection = traitlets.Enum(AxisDirection, name="Axis Direction", group="Parameters",
                                   default_value=AxisDirection.Normal, command="@0ID")

    parameterTraits = ["referenceSpeed", "acceleration", "startStopFrequency", "axisDirection", "referenceDirection"]

    def __init__(self, comport, baudRate=19200, axis_cnt=AxisCount.X):
        super().__init__()

        self._lock = Lock()
        self.comport = comport

        if os.name == 'posix':
            rm = pyvisa.ResourceManager('@py')
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

        self.axis_cnt = axis_cnt

        #    self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)

        #     self.set_trait('status', self.Status.Idle)
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

    async def __aenter__(self):
        await super().__aenter__()
        await self.initializeControlUnit()
        await self.getControlUnitInfo()
        return self

    @action("Stop")
    def stop(self):
        self.resource.write_raw(bytes([253]))
        asyncio.ensure_future(self.stopImplementation())

    async def stopImplementation(self):
        result = await self.read()
        self.set_trait("stopped", True)
        if result is None:
            return

        result = result[0:-2]
        if result == "STOP":
            self.set_trait("stopped", False)

        if not self._isMovingFuture.done():
            self._isMovingFuture.cancel()

    @action("Start")
    async def start(self):
        """
        Sends a start command to the device after it has been stopped.

        Due to weird behavior of the device, this function first executes a break command causing the device to forget
        the last movement command.
        """

        await self.softwareBreak()

        result = (await self.query("@0S"))[0]
        print("start result: " + result)
        if result == "0" or result == "G":
            self.set_trait("stopped", False)

        # await asyncio.sleep(0.1)
        await self.read()

        self.set_trait("status", self.Status.Idle)

    @action("Break")
    async def softwareBreak(self):
        self.resource.write_raw(bytes([255]))
        await self.read()

    @action("Software Reset")
    async def softwareReset(self):
        self.resource.write_raw(bytes([254]))
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

    async def initializeControlUnit(self):
        """
        Initialisation, setting number of axes.
        """
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
        result : str
            The read content of the receive buffer.
        """

        with self._lock:
            readBytes = self.readAllBytes()
            if len(readBytes) > 0:
                result = b''.join(readBytes).decode("utf-8")
                print("read(): result: " + result)
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
            print("readAllBytes: no bytes in buffer")

        while self.resource.bytes_in_buffer > 0:
            allBytes.append(self.resource.read_bytes(1))

        # some commands return "0" "handshake" before actual value
        # this is probably the wrong way to handle it
        if (allBytes[0] == b'0' and len(allBytes) != 1):
            allBytes = allBytes[1:]

        #  print("ALL Bytes",allBytes)
        return allBytes

    @threaded_async
    def query(self, command, timeout=None):
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
        list
            A list of answer strings from the device.
        """

        with self._lock:
            # remove parameter placeholders from command
            paramIndex = command.find(" {}")
            if paramIndex != -1:
                command = command[:paramIndex]

            print('ISEL_iMC_P: query ' + str(command))
            logging.info('{}: {}'.format(self, command))

            if timeout is not None:
                prevTimeout = self.resource.timeout
                self.resource.timeout = timeout

            self.resource.write(command)
            answerBytes = self.readAllBytes()
            answerString = b''.join(answerBytes).decode("utf-8")

            print('ISEL_iMC_P: answer: ' + answerString)

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

    async def executeMovementCommand(self, command):
        """
        Sends a command to the instrument that results in a movement of the axis.

        Since the IT116 can't process any other commands until the movement is completed, this function waits for the
        device's response that the movement was completed. Also sets the status to moving while the stage is moving.

        Parameters
        ----------
        command : str
            Movement command to send to the device.
        """

        self.set_trait("status", self.Status.Moving)
        result = (await self.query(command, self.MOVEMENT_TIMEOUT))[0]
        self._isMovingFuture = asyncio.Future()
        print("movement result: " + result)
        if result == "0":
            self.set_trait("status", self.Status.Idle)
            await self.statusUpdate()
        elif result == "F":
            print("movement stopped")
            logging.info('{}: {}'.format(self, "movement stopped. Press start"))
            self.set_trait("status", self.Status.Error)
        else:
            self.set_trait("status", self.Status.Error)
