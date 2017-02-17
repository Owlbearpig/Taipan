from common import Manipulator, action
import asyncio
import logging
from asyncioext import ensure_weakly_binding_future
import enum
import traitlets
from common import ureg, Q_
from queue import Queue
from math import ceil
import numpy as np


class Hydra(Manipulator):

    class StatusBits(enum.Enum):
        AxisMoving = 1 << 0
        ManualMove = 1 << 1
        MachineError = 1 << 2
        Reserved1 = 1 << 3
        Reserved2 = 1 << 4
        PosInWindow = 1 << 5
        Reserved3 = 1 << 6
        EmergencyStopped = 1 << 7
        MotorPowerDisabled = 1 << 8
        EmergencySwitchActive = 1 << 9
        DeviceBusy = 1 << 10
        Reserved4 = 1 << 11
        Reserved5 = 1 << 12
        Reserved6 = 1 << 13
        Reserved7 = 1 << 14
        InvalidStatus = 1 << 15

    identification = traitlets.Unicode('', read_only=True).tag(
                                       name='Identification')
    numberParamStack = traitlets.Int(0, read_only=True,
                                     group='Restart after Failure')

    class HydraRaw:
        def __init__(self, parent):
            self.parent = parent

        async def _read_reply(self, type):
            fut = asyncio.Future()
            self.parent._pendingReplies.put(fut)

            reply = await fut

            if type is str:
                return reply.decode('ascii')
            else:
                ret = [ type(x) for x in reply.split(b' ') ]
                if len(ret) == 1:
                    ret = ret[0]
                return ret

        def __getattr__(self, name):
            def _impl(*args, type=None, includeAxis=True, terminate=True):
                cmd = [ str(x) for x in args ]
                if includeAxis:
                    cmd.append(str(self.parent.axis))
                cmd.append(name)
                cmd = ' '.join(cmd)

                if terminate:
                    cmd += '\r\n'
                else:
                    cmd += ' '

                self.parent.transport.write(cmd.encode('ascii'))

                if type is not None:
                    return self._read_reply(type)

            return _impl


    def __init__(self, axis=1, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.transport = None
        self.axis = axis

        self._status = 0x0
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)

        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)

        self._raw = Hydra.HydraRaw(self)

    def connection_made(self, transport):
        self._buffer = b''
        self._pendingReplies = Queue()
        self.transport = transport

    def connection_lost(self, exc):
        self.transport = None

    def data_received(self, data):
        self._buffer += data

        while True:
            i = self._buffer.find(b'\n')
            if i < 0:
                break

            if not self._pendingReplies.empty():
                fut = self._pendingReplies.get()
                if not fut.done():
                    fut.set_result(self._buffer[:i+1].strip())

            self._buffer = self._buffer[i+1:]

    def eof_received(self):
        pass

    async def __aenter__(self):
        await super().__aenter__()

        if self.transport is None:
            raise RuntimeError("Can't initialize the Hydra when no connection "
                               "was made!")

        await self.initialize()
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)

        return self

    async def __aexit__(self,*args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()

    async def initialize(self):
        self.clearStack()
        self.set_trait('identification', await self._raw.nidentify(type=str))

        limits = await self._raw.getnlimit(type=float)
        self._hardwareMinimum = Q_(limits[0], 'mm')
        self._hardwareMaximum = Q_(limits[1], 'mm')
        self.velocity = Q_(await self._raw.gnv(type=float), 'mm/s')

        # 500 mm/s accelleration should be good enough
        self._raw.sna(500)

    async def updateStatus(self):
        while True:
            await self.singleUpdate()
            await asyncio.sleep(0.01)

    async def singleUpdate(self):
        movFut = self._isMovingFuture

        self._status = await self._raw.nst(type=int)
        self.set_trait('value', Q_(await self._raw.np(type=float), 'mm'))
        self.set_trait('numberParamStack',
                       await self._raw.gsp(includeAxis=False, type=int))

        self.set_trait('status',
                       self.Status.Moving
                       if bool(self._status & self.StatusBits.AxisMoving.value)
                       else self.Status.Idle)

        if self.status != self.Status.Moving and not movFut.done():
            movFut.set_result(None)

    @action('Calibrate')
    async def calibrationMove(self):
        '''
        Moves stage to lower endswitch and sets lower hardware limit to 0
        '''
        logging.debug('Hydra: Calibration Move Triggered')
        self._raw.ncal()
        if self._isMovingFuture.done():
            self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

    @action('Auto Detect Range')
    async def rangeMove(self):
        '''Finds upper hardware limit'''
        logging.debug('Hydra: Range Move Triggered')
        self._raw.nrm()
        if self._isMovingFuture.done():
            self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

    async def reference(self):
        await self.calibrationMove()
        await self.rangeMove()

    @action('Restart Axis',group='Restart after Failure')
    async def restartAxis(self):
        '''in case of emergency state, repower motor'''
        logging.debug('Hydra: Axis Restart')
        self._raw.init()

    @action('Clear Stack',group='Restart after Failure')
    def clearStack(self):
        '''Clears the controller's internal command and parameter stack'''
        logging.debug('Hydra: Command stack cleared')
        self._raw.clear()

    @action('Stop')
    def stop(self):
        self._raw.nabort()
        logging.debug('Hydra: Movement aborted')
        self._isMovingFuture.cancel()

    async def moveTo(self, val: float, velocity=None):
        await super().moveTo(val, velocity)

        if velocity is None:
            velocity = self.velocity

        self._raw.snv(velocity.to('mm/s').magnitude)

        if not self._isMovingFuture.done():
            self._isMovingFuture.cancel()

        self._isMovingFuture = asyncio.Future()

        self._raw.nm(val.to('mm').magnitude)

        await self._isMovingFuture

    async def configureTrigger(self, axis):
        axis = axis.to('mm').magnitude

        output = 1

        # 1 µs pulse width
        self._raw.settroutpw(10, output, terminate=False)
        self._raw.settroutdelay(0, output, terminate=False)
        self._raw.settroutpol(1, output, terminate=False)

        # Mode 3: Normal operation on output 1,
        #         "direction mode" operation at output 2
        # (but why do we do this? we're using output 1 anyway.)
        self._raw.settr(3, terminate=False)
        self._raw.settrpara(axis[0], axis[-1], len(axis))

        # ask for the actually set start, stop and step parameters
        paras = await self._raw.gettrpara(type=float)

        return np.linspace(paras[0], paras[1], int(paras[2])) * ureg.mm


if __name__ == '__main__':

    loop = asyncio.get_event_loop()

    async def run():
        transport, hydra = await loop.create_connection(Hydra, 'localhost',
                                                        4000)

        async with hydra:
            print("Moving to start...")
            await hydra.moveTo(Q_(20, 'mm'), Q_(10, 'mm/s'))
            await hydra.configureTrigger(Q_(0.05, 'mm'), Q_(21, 'mm'), Q_(29, 'mm'))
            print("Moving to end...")
            fut = loop.create_task(hydra.moveTo(Q_(30, 'mm'), Q_(5, 'mm/s')))
            while not fut.done():
                print("Position:", hydra.value)
                await asyncio.sleep(0.5)
            print("Done.")

    loop.run_until_complete(run())
