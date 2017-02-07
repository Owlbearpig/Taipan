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

from common import Manipulator, action
from asyncioext import ensure_weakly_binding_future
import asyncio
from traitlets import Bool, Unicode
from common import ureg, Q_
import traceback
import logging
from pint.context import Context
import uuid


class AxisAtController(Manipulator):
    _StatusMap = {
        'I': 'axis is initialized',
        'O': 'axis is disabled',
        'R': 'axis initialised and ready',
        'T': 'axis is positioning in trapezoidal profile',
        'S': 'axis is positioning in S-curve profile',
        'V': 'axis is operating in velocity mode',
        'P': 'reference motion is in progress',
        'F': 'axis is releasing a limit switch',
        'J': 'axis is operating in joystick mode',
        'L': 'axis has been disabled after approaching a hardware limit switch'
             ' (MINSTOP, MAXSTOP)',
        'B': 'axis has been stopped after approaching a brake switch (MINDEC, '
             'MAXDEC)',
        'A': 'axis has been disabled after limit switch error',
        'M': 'axis has been disabled after motion controller error',
        'Z': 'axis has been disabled after timeout error',
        'H': 'phase initialization activ (step motor axis)',
        'U': 'axis is not released.',
        'E': 'axis has been disabled after motion error',
        'W': 'axis is positioning in trapezoidal profile with WMS',
        'X': 'axis is positioning in S-curve profile with WMS',
        'Y': 'axis is operating in velocity mode with WMS',
        'C': 'axis is operating in velocity mode with continuous-path control',
        '?': 'error, unknown status of axis',
    }

    _movingStates = ['T', 'S', 'V', 'P', 'W', 'X', 'Y', 'C']

    statusMessage = Unicode(read_only=True).tag(name="Status")
    limitSwitchActive = Bool(read_only=True).tag(name="Limit switch active")
    motorPowerStageError = Bool(read_only=True).tag(
                                name="Motor power stage error")

    def __init__(self, connection=None, axis=1, pitch=Q_(1), objectName=None,
                 loop=None):
        """ Axis `axis` at connection `connection`. Has pitch `pitch` in units
        of 'full step count/length'."""
        super().__init__(objectName=objectName, loop=loop)
        self.connection = connection
        self.axis = axis
        self._status = '?'
        self.set_trait('statusMessage', self._StatusMap[self._status])
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

        self.prefPosUnit = (ureg.count / pitch).units
        self.prefVelocUnit = (ureg.count / ureg.s / pitch).units
        self.setPreferredUnits(self.prefPosUnit, self.prefVelocUnit)

        self._microstepResolution = 50
        self._pitch = pitch
        self.define_context()

        if not pitch.dimensionless:
            self.velocity = Q_(1, 'mm/s')
        else:
            self.velocity = Q_(2000, 'count/s')

    def define_context(self):
        self.contextName = 'Owis-{}'.format(uuid.uuid4())
        context = Context(self.contextName)

        if not self._pitch.dimensionless:
            context.add_transformation('', '[length]',
                                       lambda ureg, x: x / (self._pitch * self._microstepResolution))
            context.add_transformation('[length]', '[]',
                                       lambda ureg, x: x * self._pitch * self._microstepResolution)
            context.add_transformation('1/[time]', '[length]/[time]',
                                       lambda ureg, x: x / (self._pitch * self._microstepResolution))
            context.add_transformation('[length]/[time]', '1/[time]',
                                       lambda ureg, x: x * self._pitch * self._microstepResolution)

        ureg.add_context(context)

    async def __aenter__(self):
        await super().__aenter__()

        await self.send("absol" + str(self.axis))
        self._microstepResolution = await self.queryAxisVariable('mcstp')
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()

    def handleError(self, msg):
        errorCode = int(msg)
        if errorCode == 0:  # no error
            return

    async def updateStatus(self):
        while True:
            await asyncio.sleep(0.2)

            if (self.connection is None):
                continue

            try:
                await self.singleUpdate()
            except:
                logging.error(traceback.format_exc())

    async def singleUpdate(self):
        movFut = self._isMovingFuture

        self._status = (await self.send("?astat"))[self.axis - 1]
        self.set_trait('statusMessage', self._StatusMap[self._status])

        cnt = await self.queryAxisVariable('cnt') * ureg.count
        with ureg.context(self.contextName):
            cnt = cnt.to(self.prefPosUnit)
        self.set_trait('value', cnt)

        if self._status not in self._movingStates:
            self.set_trait('status', self.Status.Idle)
            if not movFut.done():
                movFut.set_result(None)
        else:
            self.set_trait('status', self.Status.Moving)

        errCode = await self.send("?err")
        if (errCode != 0):
            logging.error("OWIS Axis {} Error: {}".format(self.axis, errCode))

        estat = await self.queryAxisVariable('estat')
        self.set_trait('limitSwitchActive', bool(estat & 0xF))
        self.set_trait('motorPowerStageError', bool(estat & (1 << 4)))

    async def setAxisVariable(self, var, value):
        cmd = '{}{}={}'.format(var, int(self.axis), value)
        await self.send(cmd)

    async def queryAxisVariable(self, var):
        cmd = '?{}{}'.format(var, int(self.axis))
        return await self.send(cmd)

    async def send(self, command):
        """ Send a command to the controller. If the command is a request,
        the reply will be parsed (if possible) and returned. A error message
        is automatically sent to check for communcation errors.

        Parameters
        ----------
        command (convertible to bytearray) : The command to be sent.
        """
        if self.connection is None:
            return None

        ret = await self.connection.send(command)

        if ret is not None:
            try:
                ret = int(ret)
            except ValueError:
                pass

        errorCode = int(await self.connection.send('?msg'))
        if errorCode != 0:
            raise Exception("Message error code %d on OWIS Axis %d." %
                            (errorCode, self.axis))

        return ret

    async def moveTo(self, val: float, velocity=None):
        if velocity is None:
            velocity = self.velocity

        with ureg.context(self.contextName):
            velocity = velocity.to('count/s').magnitude

            # From the manual. 256µs is the sampling period of the encoder
            velocity *= 256e-6 * 65536

            val = val.to('count').magnitude

        await self.halt()

        await self.singleUpdate()

        self.set_trait('status', self.Status.Moving)

        await self.setAxisVariable("pvel", int(velocity))
        await self.setAxisVariable("pset", int(val))
        await self.send("pgo" + str(self.axis))

        if self._isMovingFuture.done():
            self._isMovingFuture = asyncio.Future()

        return await self._isMovingFuture

    @action("Halt", priority=0)
    async def halt(self):
        if not self._isMovingFuture.done():
            self._isMovingFuture.cancel()

        await self.send('stop' + str(self.axis))

    @action("Set Position to zero", priority=1)
    async def resetCounter(self):
        await self.send('cres' + str(self.axis))

    @action("Free from limit switch", priority=2)
    async def efree(self):
        await self.send('efree' + str(self.axis))

    @action("Home to min. lim. switch", priority=3)
    async def homeMinLim(self):
        await self.setAxisVariable('ref', 4)

    @action("Initialize", priority=4)
    async def inititialize(self):
        await self.setAxisVariable('axis', 1)
        await self.send('init' + str(self.axis))

    @action("Release axis", priority=5)
    async def releaseAxis(self):
        await self.setAxisVariable('axis', 0)

    @action("Unrelease axis", priority=6)
    async def unreleaseAxis(self):
        await self.setAxisVariable('axis', 1)

    def stop(self):
        self._loop.create_task(self.halt())

    async def reference(self):
        pass
