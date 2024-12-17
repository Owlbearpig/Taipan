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
import os
import pyvisa as visa
from threading import Lock
import traitlets
import enum
from common import Quantity
import time
from asyncioext import threaded_async, ensure_weakly_binding_future
from common import Manipulator, Q_, ureg, action


import logging

# logging.basicConfig(level=logging.DEBUG)

class Axis(enum.Enum):
    X = 1
    Y = 2
    Z = 4
    A = 8

class AxisAtController(Manipulator):

    class ReferenceDirection(enum.Enum):
        Normal = 0
        Inverse = 1

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

  #  class LimitSwitch1(enum.Enum):
   #     Disabled = 0
    #    Enabled = 1

#    class LimitSwitch2(enum.Enum):
 #       Disabled = 0
  #      Enabled = 1

 #   class ActiveLevelLimitSwitch1(enum.Enum):
  #      LowActive = 0
   #     HighActive = 1

 #   class ActiveLevelLimitSwitch2(enum.Enum):
  #      LowActive = 0
   #     HighActive = 1

    DEFAULT_TIMEOUT = 1000
    MOVEMENT_TIMEOUT = 100000
    STATUS_UPDATE_RATE = 3

    # Instrument Info Traitlets

    controlUnitInfo = traitlets.Unicode(read_only=True, name="Control Unit Info", group="Instrument Info")

    # Parameters

    # Todo: find correct default value
    referenceSpeed = traitlets.Int(name="Reference Speed", group="Parameters", default_value=900, max=2500,
                                   command="@0d")

    velocity = traitlets.Int(name="Speed", group="Absolute Movement", default_value=900)

    acceleration = Quantity(name="Acceleration", group="Parameters", default_value=Q_(100, "Hz/ms"),
                            min=Q_(1, "Hz/ms"), max=Q_(1000, "Hz/ms"), command="@0g")

    startStopFrequency = Quantity(name="Start Stop Frequency", group="Parameters",
                                  default_value=Q_(300, "Hz"), min=Q_(20, "Hz"), max=Q_(40000, "Hz"), command="@0j")

    axisDirection = traitlets.Enum(AxisDirection, name="Axis Direction", group="Parameters",
                                   default_value=AxisDirection.Normal, command="@0ID")

    referenceDirection = traitlets.Enum(ReferenceDirection, name="Reference Direction", group="Parameters",
                                        default_value=ReferenceDirection.Normal)

    stopped = traitlets.Bool(name="Stopped", default_value=False, read_only=True)
    status_disp = traitlets.Unicode(name="Status", read_only=True)

    parameterTraits = ["referenceSpeed", "acceleration", "startStopFrequency", "axisDirection", "referenceDirection"]

    def __init__(self, connection=None, axis=Axis.X, stepsPerRev=135):
        super().__init__()
        self.connection = connection
        self.axis = axis

        self.stepsPerRev = 2*stepsPerRev  # not sure if correct (@0P gives correct distance)

        self.setPreferredUnits(ureg.cm, ureg.cm / ureg.s)

        self.set_trait('status', self.Status.Idle)
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

        self.connection.register_axis(self)

    async def __aenter__(self):
        await super().__aenter__()
        await self.statusUpdate()
        self._statusUpdateFuture = ensure_weakly_binding_future(self.continuousStatusUpdate)
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._statusUpdateFuture.cancel()

    @action("Stop")
    def stop(self):
        pass
        #self.connection.resource.write_raw(bytes([253]))
        #asyncio.ensure_future(self.stopImplementation())

    async def stopImplementation(self):
        pass
        """
        result = await self.read()
        self.set_trait("stopped", True)
        if result is None:
            return

        result = result[0:-2]
        if result == "STOP":
            self.set_trait("stopped", False)

        if not self._isMovingFuture.done():
            self._isMovingFuture.cancel()
        """

    @action("Start")
    async def start(self):
        """
        Sends a start command to the device after it has been stopped.

        Due to weird behavior of the device, this function first executes a break command causing the device to forget
        the last movement command.
        """
        pass
        """
        await self.connection.softwareBreak()

        result = (await self.query("@0S"))[0]
        logging.warning()("start result: " + result)
        if result == "0" or result == "G":
            self.set_trait("stopped", False)

        # await asyncio.sleep(0.1)
        await self.read()

        self.set_trait("status", self.Status.Idle)
        """

    @action("Reference Run")
    async def referenceRun(self):
        await self.connection.referenceAxis(self.axis)

    @action("Simulate Reference Run")
    async def simulateReferenceRun(self):
        pass
        # await self.connection.write("@0N1")

    @action("Set Zero Point")
    async def setZeroPointCurrentLocation(self):
        pass
        # await self.connection.write("@0n1")

    async def continuousStatusUpdate(self):
        """
        Requests a status update every STATUS_UPDATE_RATE seconds.
        """

        while True:
            await asyncio.sleep(self.STATUS_UPDATE_RATE)
            await self.statusUpdate()

    @traitlets.observe("status")
    def status_change(self, change):
        self.set_trait("status_disp", str(change["new"].name))

    async def statusUpdate(self):
        """
        Performs a status update and updates the class attributes according to answers from the device.
        """
        logging.warning(self.status)
        if self.status != Manipulator.Status.Moving and self.status != Manipulator.Status.Error: # and not self.stopped:
            currentPosition = await self.connection.getPositions(self.axis)
            logging.warning("pos answer: " + str(currentPosition))

            self.set_trait('value', Q_(currentPosition/self.stepsPerRev, 'cm'))
            try:
                self._isMovingFuture.set_result(None)
            except asyncio.exceptions.InvalidStateError:
                pass

    async def moveTo(self, val: float, velocity=None):
        if self.stopped:
            logging.info("Device is stopped. Can't process commands until started")
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
            # logging.warning()("speed: " + str(velocity))

        self.set_trait("status", self.Status.Moving)

        results = await self.connection.executeMovementCommand(self.axis, val, velocity)
        logging.warning("movement result: " + " ".join(results))
        result = results[0]
        self._isMovingFuture = asyncio.Future()
        logging.warning("movement result: " + result)
        if result == "0":
            self.set_trait("status", self.Status.Idle)
            await self.statusUpdate()
        elif result == "F":
            logging.warning("movement stopped")
            logging.warning('{}: {}'.format(self, "movement stopped. Press start"))
            self.set_trait("status", self.Status.Error)
        else:
            self.set_trait("status", self.Status.Error)

        self.__blockTargetValueUpdate = False

    async def waitForTargetReached(self):
        return await self._isMovingFuture



