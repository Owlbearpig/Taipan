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

from taipan.common import Manipulator, action, Q_, ureg
from taipan.common.traits import Quantity
import asyncio
import ctypes
import enum
import traitlets
import logging
import os
from taipan.asyncioext import ensure_weakly_binding_future


class GonioConn:
    class BoardType(enum.Enum):
        ISA = 1
        PC104 = 2
        AT9610 = 4
        AT96 = 8
        PCI = 16

    class wPCLType(enum.Enum):
        PCL80 = 0
        PCL240AK = 1
        PCL240AS = 2

    def __init__(self, board_number=0):
        dllpath = os.getcwd() + '\\thirdparty\\goniometerdlls'
        os.environ['PATH'] += os.pathsep + dllpath
        self.dll = ctypes.WinDLL(dllpath + '\\smc_pc72.dll')
        self.noAxes = 0
        wError = self.dll.Init()
        if wError == 0:
            logging.info('Initializing Goniometer dll succesfull')
        else:
            logging.info('Initializing Goniometer dll failed')
        boards, noBoards = self._discoverBoards()
        if board_number > noBoards:
            logging.info('Cannot initialize Board number {}, only {} boards ' +
                         'found!'.format(board_number, noBoards))
        else:
            self.noAxes = self._discoverAxis(boards[board_number])

    def _discoverBoards(self):
        boards = (ctypes.c_uint32*16)()
        noBoards = self.dll.FindPCIBoards(boards)
        if noBoards == 0:
            logging.info('No PCI boards found!')
        else:
            logging.info('Found {} boards'.format(noBoards))
        return boards, noBoards

    def _discoverAxis(self, board, boardtype=BoardType.PCI,
                      ICType=wPCLType.PCL240AS):
        noAxes = self.dll.InitBoard(boardtype.value, board, ICType.value)
        logging.info('Number of connected axes at board {}: {}'
                     .format(board, noAxes))
        return noAxes

    def __del__(self):
        self.dll.DeInit()
        logging.info('Goniometer driver DeInitialized')


class Goniometer(Manipulator):

    class EncoderMode(enum.Enum):
        A_BSignal1fold = 0xC0
        A_BSignal2fold = 0xE0
        A_BSignal4fold = 0xF0

    class Ramping(enum.Enum):
        Ramping = 0
        NoRamping = 1

    Errors = {
        170: 'Maximum relative positioning Distance Exceeded',
        175: 'Minimum relative positioning Distance Exceeded',
        1200: 'Acceleration too steep',
        1201: 'deceleration too steep',
        1250: 'acceleration too flat',
        1251: 'deceleration too flat',
        1300: 'speed value too high',
        1350: 'speed value too low',
        9000: 'Axis not ready'
    }

    connection = None
    positiveLimitSwitch = traitlets.Bool(False,
                                         read_only=True).tag(group='Status')
    negativeLimitSwitch = traitlets.Bool(False,
                                         read_only=True).tag(group='Status')
    calibrateToDegree = Quantity(Q_(0, 'deg'), read_only=False)
    calibrateToDegree.tag(group='Status')

    isMoving = traitlets.Bool(False, read_only=True).tag(group='Status')
    startSpeed = Quantity(Q_(0.25, 'deg/s')).tag(group='Velocity Settings')
    acceleration = Quantity(Q_(0.0125, 'deg/s**2'))
    acceleration.tag(group='Velocity Settings')
    deceleration = Quantity(Q_(0.0125, 'deg/s**2'))
    deceleration.tag(group='Velocity Settings')

    def __init__(self, axis=0, encoderMode=EncoderMode.A_BSignal4fold,
                 objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.setPreferredUnits(ureg.deg, ureg.deg / ureg.s)
        if Goniometer.connection is None:
            Goniometer.connection = GonioConn()
        self.cdll = Goniometer.connection.dll

        self.axis = axis
        self.cdll.InitEncoder(self.axis, encoderMode.value)
        self.cdll.SetEncoder(self.axis, 0)
        self.cdll.SetRunFreeFrq(self.axis, 100)
        self.cdll.SetRunFreeSteps(self.axis, 32000)

        # don't know if important
        self.cdll.SetPosition(self.axis, 0)
        self.set_trait('value', self._stepToDeg(
                                             self.cdll.GetPosition(self.axis)))
        self.velocity = Q_(5, 'deg/s')

        self._statusRefresh = 0.1
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)

    async def updateStatus(self):
        while True:
            await asyncio.sleep(self._statusRefresh)
            if (Goniometer.connection is None):
                continue
            await self.singleUpdate()

    async def singleUpdate(self):
        steps = self.cdll.GetPosition(self.axis)
        self.set_trait('value', self._stepToDeg(steps))
        ls = self.cdll.GetLSStatus(self.axis)
        self.set_trait('positiveLimitSwitch', bool(ls & 1))
        self.set_trait('negativeLimitSwitch', bool(ls & 2))

        self.set_trait('isMoving',
                       not bool(self.cdll.GetReadyStatus(self.axis)))
        if self.isMoving:
            self.set_trait('status', self.Status.Moving)
        else:
            self.set_trait('status', self.Status.Idle)
            if not self._isMovingFuture.done():
                self._isMovingFuture.set_result(None)

    async def __aexit__(self, *args):
        self.stop()
        self._updateFuture.cancel()
        await super().__aexit__(*args)

    @action("Stop")
    def stop(self, stopMode=Ramping.Ramping):
        self.cdll.StopMotion(self.axis, stopMode.value)
        self._isMovingFuture.cancel()

    #@action("Reference")
    async def reference(self):
        if self.isMoving:
            logging.info('{} {}: Please finish'.format(self, self.axis) +
                         'movement before searching Limit Switch')
            return False

        self._setSpeedProfile(Q_(5, 'deg/s'))
        self.cdll.SetRunFreeFrq(self.axis, 100)
        self.cdll.SetRunFreeSteps(self.axis, 32000)

        self.cdll.SearchLS(self.axis, ord('-'))

        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

        self.cdll.FindLS(self.axis, ord('-'))
        self.cdll.RunLSFree(self.axis, ord('-'))

        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

        self.cdll.SetPosition(self.axis, 0)

    def _setSpeedProfile(self, velocity):
        ss = int(self.startSpeed.to('deg/s').magnitude*400)
        fs = int(velocity.to('deg/s').magnitude*400)
        ac = int(self.acceleration.to('deg/s**2').magnitude*400)
        dc = int(self.deceleration.to('deg/s**2').magnitude*400)
        error = self.cdll.SetSpeedProfile(self.axis, ss, fs, ac, dc)
        if error != 0:
            error = self.cdll.SetSpeedProfile(self.axis, 100, 2000, 5, 5)
            logging.error('{} {}: '.format(self, self.axis) +
                          Goniometer.Errors.get(error))
            logging.error('{} {}: Setting Speed command ignored'
                          .format(self, self.axis))
            return False
        else:
            return True

    async def moveTo(self, val: float, velocity=None):
        if velocity is None:
            velocity = self.velocity

        # The Goniometer ignores new position commands, if the stage is moving
        if self.isMoving:
            self.stop()
            while self.status != self.Status.Idle:
                await asyncio.sleep(0)

        error = self.cdll.SetDestination(self.axis, self._degToStep(val),
                                         ord('a'))

        if error != 0:
            logging.error('{} {}: '.format(self, self.axis) +
                          Goniometer.Errors.get(error))
            logging.error('{} {}: Positioning Command ignored'
                          .format(self, self.axis))
            return False

        self._setSpeedProfile(velocity)

        error = self.cdll.StartMotion(self.axis,
                                      Goniometer.Ramping.Ramping.value)
        if error != 0:
            logging.error('{} {}: '.format(self, self.axis) +
                          Goniometer.Errors.get(error))
            logging.error('{} {}: Positioning Command ignored'
                          .format(self, self.axis))
            return False

        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

    @action('Set Calibration')
    def calibrate(self, value=None):
        if value is None:
            value = self.calibrateToDegree
        self.cdll.SetPosition(self.axis, self._degToStep(value))

    def _degToStep(self, degs):
        return int(degs.to('deg').magnitude*400)

    def _stepToDeg(self, steps):
        return Q_(steps/400.0, 'deg')
