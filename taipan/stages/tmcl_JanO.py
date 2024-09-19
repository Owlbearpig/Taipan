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

5.5.2020 JanO
Step-angle relation modified here for a special holder for 
transmission measurements through a sample which needs to be rotated.
check functions _angle2steps and steps2angles

You should have received a copy of the GNU General Public License
along with Taipan.  If not, see <http://www.gnu.org/licenses/>.
"""

import asyncio
from threading import Lock
from thirdparty.PyTMCL.TMCL.communication import TMCLCommunicator
from common import Manipulator, Q_, ureg, action
from traitlets import Enum as EnumTrait
from traitlets import Bool as BoolTrait
from enum import Enum
from common.traits import Quantity
from asyncioext import threaded_async, ensure_weakly_binding_future


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
        
    class Direction(Enum):
        Positive = 1
        Negative = -1
        
    _DirectionMap = {Direction.Positive: 1, Direction.Negative: -1}

    class Direction(Enum):
        Positive = 1
        Negative = -1

    _DirectionMap = {Direction.Positive: 1, Direction.Negative: -1}

    stepAngle = EnumTrait(StepAngle, StepAngle.Step_1_8).tag(name="Step angle")
    angularAcceleration = Quantity(Q_(100), min=Q_(0), max=Q_(2047)).tag(
                              name='Acceleration', priority=1)
    microSteps = EnumTrait(Microsteps, Microsteps.Microsteps_64).tag(
                              name="Microstepping")
    direction = EnumTrait(Direction, Direction.Negative).tag(
                              name="Direction")

    value = Quantity(Q_(0, "mm"), read_only=True).tag(name="Value")
    velocity = Quantity(Q_(1, "mm/s")).tag(name="Velocity")

    referenceable = BoolTrait(False, read_only=True, help="Whether the Stage has a "  # added by CM
                                                          "Reference switch").tag(name="Referenceable")

    def __init__(self, port, baud=9600, axis=0, objectName=None, loop=None, implementation=None):
        super().__init__(objectName=objectName, loop=loop)

        self.comm_lock = Lock()
        self.comm = TMCLCommunicator(port, 1, 4, 0,
                                     float('inf'), float('inf'), float('inf'))
        self.comm._ser.baudrate = baud
        self.axis = axis
        
        self.implementation = implementation # JanO
        if implementation != 'Linear_mm':
            print("Limits only implemented for linear implementation. Comment out targetValue trait")
            

        self.implementation = implementation  # JanO

        if implementation is None:
            self.setPreferredUnits(ureg.deg, ureg.deg / ureg.s)
            self.velocity = Q_(100, 'deg/s')
            self.set_trait('value', Q_(0, 'deg'))
            self.unit = 'deg'
            self.convFactor2 = 1
            self.convFactor3 = self.convFactor2
        elif implementation=='Rotator':
            self.convFactor2 = 180/1963
            self.setPreferredUnits(ureg.deg, ureg.deg / ureg.s)            
            self.velocity = Q_(500*self.convFactor2//1, 'deg/s')
            self.set_trait('value', Q_(0, 'deg'))
            self.convFactor3 = self.convFactor2
            self.unit = 'deg'
            
        elif implementation=='Linear_mm':
            self.convFactor2 = (24.45-2.35)/16000
            self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)            
            self.velocity = Q_((500*self.convFactor2*100)//10/10, 'mm/s')
            self.set_trait('value', Q_(0, 'mm'))
            self.convFactor3 = self.convFactor2
            self.unit = 'mm'
        
        # JanO: added on 23.11.2022 for a specific linear translation  (ACCUDEX)
        # based on a stepper motor (TMCL) with endswitches. One could add 
        # the option of referencing (drive to an end switch)
        elif implementation=='Linear_mm_ACCUDEX':
            #self.convFactor = 204
            self.convFactor2 = 204.5/36830 #mm/deg
            # 500 deg/s => took 97 s to move 204.5 mm- 2.11 mm/S
            self.convFactor3 = 2.11/500
            self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)            
            self.velocity = Q_((237*self.convFactor3*100)//10/10, 'mm/s')
            self.set_trait('value', Q_(0, 'mm'))
            self.unit = 'mm'
            self.direction = self.Direction.Positive
            
        else:
            self.setPreferredUnits(ureg.deg, ureg.deg / ureg.s)
            self.velocity = Q_(100, 'deg/s')
            self.set_trait('value', Q_(0, 'deg'))
            self.unit = 'deg'
            self.convFactor2 = 1
            self.convFactor3 = self.convFactor2
            print('Warning - the selected type of TMCL implementation is not implemented')

        self.set_trait('status', self.Status.Idle)
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

    def _angle2steps(self, angle):
        #convFactor = 0.9 if self.stepAngle == self.StepAngle.Step_0_9 else 1.8
        convFactor = 1.8
        return angle * self._MicroStepMap[self.microSteps] / convFactor /self.convFactor2

    def _steps2angle(self, steps):
        convFactor = 1.8
        # print(self.angularAcceleration)
        return steps * convFactor * self.convFactor2 / self._MicroStepMap[self.microSteps]

    async def waitForTargetReached(self, timeout=30):  # coppied from PI by JanO for TabularScan
        return await self._isMovingFuture

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

    # --- added by CM
    @threaded_async
    def _mst(self, target):  # motor stop
        with self.comm_lock:
            self.comm.mst(self.axis)

    @threaded_async
    def _rfs(self):  # reference search
        if (self.referenceable):
            with self.comm_lock:
                self.comm.rfs(self.axis, 'START')  # commands 'STATUS','END' also exist

    # ---

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
        self.set_trait('value', self._DirectionMap[self.direction] * Q_(self._steps2angle(stepPos), self.unit))

        movFut = self._isMovingFuture

        if not movFut.done():
            # check for target reached
            reached = await self._get_param(8)
            if reached and not movFut.done():
                movFut.set_result(None)

    async def moveTo(self, val, velocity=None):
        if velocity is None:
            velocity = self.velocity
        
        velocity = velocity.magnitude/self.convFactor3
        val = self._DirectionMap[self.direction] * self._angle2steps(val.to(self.unit).magnitude)

        velocity = velocity.magnitude / self.convFactor3
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

    @action("Halt", priority=0)  # added by CM to be interactive
    def stop(self):
        with self.comm_lock:
            self.comm.mst(self.axis)

        if not self._isMovingFuture.done():  # added by CM
            self._isMovingFuture.cancel()

    # --- added by CM
    @action("Set Position to zero", priority=1)
    async def setPositionToZero(self):
        await self._set_param(1, 0)

    @action("Home min. lim. switch", priority=3)
    async def homeMinLim(self):
        if (self.referenceable):
            await self._rfs()
    # ---


if __name__ == '__main__':
    loop = asyncio.get_event_loop()


    async def run():
        async with TMCL('/dev/ttyUSB0') as stepper:
            print("moving.")
            await stepper.moveTo(Q_(360, 'deg'))
            await stepper.moveTo(Q_(0, 'deg'))
            print("moving done.!")


    loop.run_until_complete(run())

'''
    def _angle2steps(self, angle):
        convFactor = 0.9 if self.stepAngle == self.StepAngle.Step_0_9 else 1.8
        if self.implementation is None:
            factor2 = 1
        elif self.implementation == 'Rotator':
            factor2 = 2*self.conv_factor if self.stepAngle == self.StepAngle.Step_0_9 else self.conv_factor
        elif self.implementation == 'Linear_mm': 
            factor2 = 2*self.conv_factor if self.stepAngle == self.StepAngle.Step_0_9 else self.conv_factor
        else:
            factor2 = 1
            print('Warning - the selected type of TMCL implementation is not implemented')
        return angle * self._MicroStepMap[self.microSteps] / convFactor /factor2

    def _steps2angle(self, steps):
        convFactor = 0.9 if self.stepAngle == self.StepAngle.Step_0_9 else 1.8
        if self.implementation is None:
            factor2 = 1
        elif self.implementation == 'Rotator':
            factor2 = 2*self.conv_factor if self.stepAngle == self.StepAngle.Step_0_9 else self.conv_factor
        elif self.implementation == 'Linear_mm': 
            factor2 = 2*self.conv_factor if self.stepAngle == self.StepAngle.Step_0_9 else self.conv_factor
        else:
            factor2 = 1
            print('Warning - the selected type of TMCL implementation is not implemented')
        return steps * convFactor * factor2 / self._MicroStepMap[self.microSteps]
'''