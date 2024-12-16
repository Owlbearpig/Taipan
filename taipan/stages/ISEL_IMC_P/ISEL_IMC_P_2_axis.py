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
import asyncio
import logging
import os
from threading import Lock

import pyvisa
import traitlets


from asyncioext import ensure_weakly_binding_future
from common import Manipulator, Q_, action
from stages.ISEL_IMC_P import Connection


class ISEL_iMC_P_X_Axis(Manipulator):

    # Relative Movement
    relativeMovementPath = traitlets.Int(name="Movement Path", group="Relative Movement", default_value=0)
    relativeMovementSpeed = traitlets.Int(name="Speed", group="Relative Movement", default_value=900)

    # Absolute Movementx
    absoluteMovementPosition = traitlets.Int(name="Target Position", group="Absolute Movement", default_value=0)
    absoluteMovementSpeed = traitlets.Int(name="Speed", group="Absolute Movement", default_value=900)

    stopped = traitlets.Bool(name="Stopped", default_value=False, read_only=True)


    def __init_(self, comport, baudRate, stepsPerRev, objectName, loop):
        super().__init__(comport,baudRate,stepsPerRev,objectName,loop)

        self._lock = Lock()

        self.observe(self.setParameterOnDevice, self.parameterTraits)


        if os.name == 'posix':
            rm = pyvisa.ResourceManager('@py')
        elif os.name == 'nt':
            rm = pyvisa.ResourceManager()

        try:
            self.resource = rm.open_resource(comport)
        except pyvisa.errors.VisaIOError:
            raise Exception('Failed to open ISEL_iMC_P stage at comport: ' + comport)


    async def __aenter__(self):
        await super().__aenter__()
        await self.statusUpdate()
        self._statusUpdateFuture = ensure_weakly_binding_future(self.continuousStatusUpdate)
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._statusUpdateFuture.cancel()

    @action("Reference Run")
    async def referenceRun(self):
        await self.executeMovementCommand("@0R1")

    @action("Simulate Reference Run")
    async def simulateReferenceRun(self):
        await self.write("@0N1")

    @action("Set Zero Point")
    async def setZeroPointCurrentLocation(self):
        await self.write("@0n1")

    @action("Move", group="Absolute Movement")
    async def moveAbsolute(self):
        await self.moveTo(self.absoluteMovementPosition, self.absoluteMovementSpeed)

    @action("Move", group="Relative Movement")
    async def moveRelative(self):
        command = "@0A" + str(self.relativeMovementPath) + "," + str(self.relativeMovementSpeed)
        await self.executeMovementCommand(command)

    async def statusUpdate(self):
        """
        Performs a status update and updates the class attributes according to answers from the device.
        """

        if self.status != Manipulator.Status.Moving and self.status != Manipulator.Status.Error: # and not self.stopped:
            currentPosition = (await self.query("@0P"))[0]
           # print("current pos",currentPosition[0:6])
            currentPosition = int(currentPosition[0:6], 16)
            print("pos answer: " + str(currentPosition))

            self.set_trait('value', Q_(currentPosition/self.stepsPerRev, 'cm'))
            try:
                self._isMovingFuture.set_result(None)
            except asyncio.exceptions.InvalidStateError:
                pass

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
        self._lock = Lock()
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

    async def continuousStatusUpdate(self):
        """
        Requests a status update every STATUS_UPDATE_RATE seconds.
        """

        while True:
            await asyncio.sleep(self.STATUS_UPDATE_RATE)
            await self.statusUpdate()

    async def moveTo(self, val: float, velocity=None):
        if self.stopped:
            print("Device is stopped. Can't process commands until started")
            return

        self.__blockTargetValueUpdate = True

        if velocity is None:
            velocity = self.velocity

        if not isinstance(val, int) and not isinstance(val, float):
            val = val.to("cm").magnitude
            val *= self.stepsPerRev

        val = int(val)

        if not isinstance(velocity, int) and not isinstance(velocity, float):
            velocity = velocity.to('cm/s').magnitude
            velocity *= 1600  # self.stepsPerRev ?
            velocity = int(velocity)
            # print("speed: " + str(velocity))

        command = "@0M" + str(val) + "," + str(velocity)
        await self.executeMovementCommand(command)

        self.__blockTargetValueUpdate = False



class ISEL_iMC_P_Y_Axis(Manipulator):

    # Relative Movement
    relativeMovementPath = traitlets.Int(name="Movement Path", group="Relative Movement", default_value=0)
    relativeMovementSpeed = traitlets.Int(name="Speed", group="Relative Movement", default_value=900)

    # Absolute Movement
    absoluteMovementPosition = traitlets.Int(name="Target Position", group="Absolute Movement", default_value=0)
    absoluteMovementSpeed = traitlets.Int(name="Speed", group="Absolute Movement", default_value=900)

    stopped = traitlets.Bool(name="Stopped", default_value=False, read_only=True)

    def __init_(self, comport, baudRate, stepsPerRev, objectName, loop):
        super().__init__(comport,baudRate,stepsPerRev,objectName,loop)

        self._lock = Lock()
        if os.name == 'posix':
            rm = pyvisa.ResourceManager('@py')
        elif os.name == 'nt':
            rm = pyvisa.ResourceManager()

        try:
            self.resource = rm.open_resource(comport)
        except pyvisa.errors.VisaIOError:
            raise Exception('Failed to open ISEL_iMC_P stage at comport: ' + comport)

    async def __aenter__(self):
        await super().__aenter__()
        await self.statusUpdate()
        self._statusUpdateFuture = ensure_weakly_binding_future(self.continuousStatusUpdate)
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._statusUpdateFuture.cancel()

    @action("Reference Run")
    async def referenceRun(self):
        await self.executeMovementCommand("@0R2")

    @action("Simulate Reference Run")
    async def simulateReferenceRun(self):
        await self.write("@0N2")

    @action("Set Zero Point")
    async def setZeroPointCurrentLocation(self):
        await self.write("@0n2")

    @action("Move", group="Absolute Movement")
    async def moveAbsolute(self):
        await self.moveTo(self.absoluteMovementPosition, self.absoluteMovementSpeed)

    @action("Move", group="Relative Movement")
    async def moveRelative(self):
        command = "@0A" +str(0)+ "," +str(0)+ "," + str(self.relativeMovementPath) + "," + str(self.relativeMovementSpeed)
        await self.executeMovementCommand(command)

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
        self._lock = Lock()
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

    async def continuousStatusUpdate(self):
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

        if self.status != Manipulator.Status.Moving and self.status != Manipulator.Status.Error: # and not self.stopped:
            currentPosition = (await self.query("@0P"))[0]
            currentPosition = int(currentPosition[6:12], 16)
            print("pos answer: " + str(currentPosition))

            self.set_trait('value', Q_(currentPosition/self.stepsPerRev, 'cm'))
            try:
                self._isMovingFuture.set_result(None)
            except asyncio.exceptions.InvalidStateError:
                pass

    async def moveTo(self, val: float, velocity=None):
        if self.stopped:
            print("Device is stopped. Can't process commands until started")
            return

        self.__blockTargetValueUpdate = True

        if velocity is None:
            velocity = self.velocity

        if not isinstance(val, int) and not isinstance(val, float):
            val = val.to("cm").magnitude
            val *= self.stepsPerRev

        val = int(val)

        if not isinstance(velocity, int) and not isinstance(velocity, float):
            velocity = velocity.to('cm/s').magnitude
            velocity *= 1600  # self.stepsPerRev ?
            velocity = int(velocity)
            # print("speed: " + str(velocity))

        command = "@0M" +str(0) +","+ str(0)+ ","+ str(val) + "," + str(velocity)
        await self.executeMovementCommand(command)

        self.__blockTargetValueUpdate = False


