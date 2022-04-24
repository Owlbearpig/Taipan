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
from threading import Lock
from taipan.thirdparty.PyTMCL.TMCL.communication import TMCLCommunicator
from taipan.common import Manipulator, Q_, ureg
from traitlets import Enum as EnumTrait
from enum import Enum
from taipan.common.traits import Quantity
from taipan.asyncioext import threaded_async, ensure_weakly_binding_future


class TMCL(Manipulator):

    class StepAngle(Enum):
        Step_0_9 = 0
        Step_1_8 = 1

    class Microsteps(Enum):
        FullStep = 0
        HalfStep = 1
        Microsteps_4 = 2
        Microsteps_8 = 3
        Microsteps_16 = 4
        Microsteps_32 = 5
        Microsteps_64 = 6

    _MicroStepMap = {
        Microsteps.FullStep: 1,
        Microsteps.HalfStep: 2,
        Microsteps.Microsteps_4: 4,
        Microsteps.Microsteps_8: 8,
        Microsteps.Microsteps_16: 16,
        Microsteps.Microsteps_32: 32,
        Microsteps.Microsteps_64: 64
    }

    stepAngle = EnumTrait(StepAngle, StepAngle.Step_1_8).tag(name="Step angle")
    angularAcceleration = Quantity(Q_(100), min=Q_(0), max=Q_(2047)).tag(
                              name='Acceleration')
    microSteps = EnumTrait(Microsteps, Microsteps.Microsteps_64).tag(
                              name="Microstepping")

    def __init__(self, port, baud=9600, axis=0, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)

        self.comm_lock = Lock()
        self.comm = TMCLCommunicator(port, 1, 4, 0,
                                     float('inf'), float('inf'), float('inf'))
        self.comm._ser.baudrate = baud
        self.axis = axis

        self.setPreferredUnits(ureg.deg, ureg.dimensionless)

        self.velocity = Q_(20)
        self.set_trait('value', Q_(0, 'deg'))

        self.set_trait('status', self.Status.Idle)
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

    def _angle2steps(self, angle):
        convFactor = 0.9 if self.stepAngle == self.StepAngle.Step_0_9 else 1.8
        return angle * self._MicroStepMap[self.microSteps] / convFactor

    def _steps2angle(self, steps):
        convFactor = 0.9 if self.stepAngle == self.StepAngle.Step_0_9 else 1.8
        return steps * convFactor / self._MicroStepMap[self.microSteps]

    @threaded_async
    def _get_param(self, param):
        with self.comm_lock:
            return self.comm.gap(self.axis, param)

    @threaded_async
    def _set_param(self, param, value):
        with self.comm_lock:
            self.comm.sap(self.axis, param, value)

    @threaded_async
    def _mvp(self, target):
        with self.comm_lock:
            self.comm.mvp(self.axis, 'ABS', target)

    async def __aenter__(self):
        await super().__aenter__()
        self._updateFuture = ensure_weakly_binding_future(self._update)
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()

    async def _update(self):
        while True:
            await asyncio.sleep(0.2)
            await self._singleUpdate()

    async def _singleUpdate(self):
        stepPos = await self._get_param(1)
        self.set_trait('value', Q_(self._steps2angle(stepPos), 'deg'))

        movFut = self._isMovingFuture

        if not movFut.done():
            # check for target reached
            reached = await self._get_param(8)
            if reached and not movFut.done():
                movFut.set_result(None)

    async def moveTo(self, val, velocity=None):
        if velocity is None:
            velocity = self.velocity

        val = self._angle2steps(val.to('deg').magnitude)
        velocity = velocity.magnitude
        accel = self.angularAcceleration.magnitude

        if not self._isMovingFuture.done():
            self.stop()

        # set microstep resolution (param 140)
        await self._set_param(140, self.microSteps.value)

        # set max. positioning speed (param 4) and acceleration (param 5)
        await self._set_param(4, velocity)
        await self._set_param(5, accel)

        # move to target
        await self._mvp(val)

        self.set_trait('status', self.Status.Moving)
        self._isMovingFuture = asyncio.Future()

        def _set_status(future):
            self.set_trait('status', self.Status.Idle)

        self._isMovingFuture.add_done_callback(_set_status)

        await self._isMovingFuture

    def stop(self):
        with self.comm_lock:
            self.comm.mst(self.axis)

        self._isMovingFuture.cancel()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    async def run():
        async with TMCL('/dev/ttyUSB0') as stepper:
            print("moving.")
            await stepper.moveTo(Q_(360, 'deg'))
            await stepper.moveTo(Q_(0, 'deg'))
            print("moving done.!")

    loop.run_until_complete(run())
