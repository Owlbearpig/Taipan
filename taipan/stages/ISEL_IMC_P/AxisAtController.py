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
from .Controller import Controller


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

    velocity = Quantity(Q_(2, "cm/s"), name="Speed", max=Q_(10, "cm/s"),
                        min=Q_(0, "cm/s")).tag(name="velocity")

    acceleration = Quantity(name="Acceleration", group="Parameters", default_value=Q_(100, "Hz/ms"),
                            min=Q_(1, "Hz/ms"), max=Q_(1000, "Hz/ms"), command="@0g")

    startStopFrequency = Quantity(name="Start Stop Frequency", group="Parameters",
                                  default_value=Q_(300, "Hz"), min=Q_(20, "Hz"), max=Q_(40000, "Hz"), command="@0j")

    axisDirection = traitlets.Enum(AxisDirection, name="Axis Direction", group="Parameters",
                                   default_value=AxisDirection.Normal, command="@0ID")

    referenceDirection = traitlets.Enum(ReferenceDirection, name="Reference Direction", group="Parameters",
                                        default_value=ReferenceDirection.Normal)

    status_disp = traitlets.Unicode(name="Status", read_only=True)

    parameterTraits = ["referenceSpeed", "acceleration", "startStopFrequency", "axisDirection", "referenceDirection"]

    def __init__(self, connection : Controller, axis=Axis.X, stepsPerRev=135):
        super().__init__()
        self.connection = connection
        self.axis = axis

        self.stepsPerRev = 2*stepsPerRev  # not sure if correct (@0P gives correct distance)

        self.setPreferredUnits(ureg.cm, ureg.cm / ureg.s, block_move=True)

        self.set_trait("status", self.Status.Idle)
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
    async def stop(self):
        self.connection.resource.write_raw(bytes([253]))
        self.set_trait("status", self.Status.Error)

    @action("Start")
    async def start(self):
        """
        Sends a start command to the device after it has been stopped.

        Due to weird behavior of the device, this function first executes a break command causing the device to forget
        the last movement command.
        """
        await self.connection.softwareBreak()

        result = await self.connection.query("@0S")
        if not result[0]:
            self.set_trait("status", self.Status.Idle)


    @action("Reference Run")
    async def referenceRun(self):
        # TODO set status moving when referencing
        await self.connection.referenceAxis(self.axis)
        await self.statusUpdate()

    @action("Set Zero Point")
    async def setZeroPointCurrentLocation(self):
        await self.connection.setZero(self.axis)
        self.set_trait("value", Q_(0, self.trait_metadata("value", "preferred_units")))

    async def continuousStatusUpdate(self):
        """
        Requests a status update every STATUS_UPDATE_RATE seconds.
        """

        while True:
            await asyncio.sleep(self.STATUS_UPDATE_RATE)
            await self.statusUpdate()

    @traitlets.observe("status")
    def statusChange(self, change):
        self.set_trait("status_disp", str(change["new"].name))

    async def statusUpdate(self):
        """
        Performs a status update and updates the class attributes according to answers from the device.
        """
        if self.connection.has_error:
            self.set_trait("status", self.Status.Error)
            return
        if self.status != Manipulator.Status.Moving and self.status != Manipulator.Status.Error: # and not self.stopped:
            currentPosition = await self.connection.getPositions(self.axis)
            if not currentPosition:
                return
            self.set_trait("value", Q_(currentPosition/self.stepsPerRev, self.value.units))

    async def moveTo(self, val : Q_, velocity=None):

        val_unit = self.trait_metadata("value", "preferred_units")
        vel_unit = self.trait_metadata("velocity", "preferred_units")

        self.__blockTargetValueUpdate = True

        if velocity is None:
            velocity = self.velocity

        if isinstance(val, Q_):
            val = val.to(val_unit).magnitude
            val *= self.stepsPerRev

        steps = int(val)

        if isinstance(velocity, Q_):
            velocity = velocity.to(vel_unit).magnitude
            velocity *= 1600  # self.stepsPerRev ?
            velocity = int(velocity)
            # logging.warning()("speed: " + str(velocity))
        logging.warning("speed: " + str(velocity))
        self.set_trait("status", self.Status.Moving)

        move_result = await self.connection.executeMovementCommand(self.axis, steps, velocity)
        self._isMovingFuture = asyncio.Future()

        if not move_result[0]:
            try:
                self._isMovingFuture.set_result(None)
            except asyncio.exceptions.InvalidStateError:
                pass
            self.set_trait("status", self.Status.Idle)
            await self.statusUpdate()
        else:
            self.set_trait("status", self.Status.Error)

        self.__blockTargetValueUpdate = False

    async def waitForTargetReached(self):
        return await self._isMovingFuture



