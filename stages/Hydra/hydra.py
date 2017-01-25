from common import Manipulator, action
import asyncio
import logging, warnings
from threading import Lock
from asyncioext import threaded_async, ensure_weakly_binding_future
import enum
import traitlets
from common import ureg, Q_
from queue import Queue


'''
0: Controler
1: Axis 1
2: Axis 2 not connected!
3: Sensor
'''

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

        print("CL window size:", await self._raw.getclwindow(type=float))
        print("CL window time:", await self._raw.getclwintime(type=float))

        limits = await self._raw.getnlimit(type=float)
        self._hardwareMinimum = Q_(limits[0], 'mm')
        self._hardwareMaximum = Q_(limits[1], 'mm')
        self.velocity = Q_(await self._raw.gnv(type=float), 'mm/s')

    async def updateStatus(self):
        while True:
            await self.singleUpdate()
            await asyncio.sleep(0.1)

    async def singleUpdate(self):
        self._status = await self._raw.nst(type=int)
        self.set_trait('value', Q_(await self._raw.np(type=float), 'mm'))
        self.set_trait('numberParamStack',
                       await self._raw.gsp(includeAxis=False, type=int))

        if (not bool(self._status & self.StatusBits.AxisMoving.value) and
            not self._isMovingFuture.done()):
                self._isMovingFuture.set_result(None)

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

    async def beginScan(self, start, stop, velocity=None):
        logging.debug('Hydra: begin Scan called')
        start = start.to('mm')
        stop = stop.to('mm')
        velocity = velocity.to('mm/s')

        # 0.75 mm buffer for acceleration and proper trigger position
        if stop > start:
            await self.moveTo(start - Q_(0.75, 'mm'), velocity)
        else:
            await self.moveTo(start + Q_(0.75, 'mm'), velocity)

    @action('Stop')
    async def stop(self):
        self._raw.nabort()
        logging.debug('Hydra: Movement aborted')
        self._isMovingFuture.cancel()

    async def moveTo(self, val: float, velocity=None):
        logging.debug('Hydra: Move To {:.3f~}'.format(val.to('mm')))

        if velocity is None:
            velocity = self.velocity

        self._raw.snv(velocity.to('mm/s').magnitude)
        self._raw.nm(val.to('mm').magnitude)

        if self._isMovingFuture.done():
            self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

    async def configureTrigger(self, step, start=None, stop=None):
        step = step.to('mm').magnitude
        start = start.to('mm').magnitude
        stop = stop.to('mm').magnitude

        N = int((stop - start) / step) + 1

        output = 1

        # 1 µs pulse width
        self._raw.settroutpw(1, output, termiante=False)
        self._raw.settroutdelay(0, output, terminate=False)
        self._raw.settroutpol(1, output, terminate=False)

        # Mode 3: Normal operation on output 1,
        #         "direction mode" operation at output 2
        # (but why do we do this? we're using output 1 anyway.)
        self._raw.settr(3, termiante=False)
        self._raw.settrpara(start, stop, N)

        # ask for the actually set start, stop and step parameters
        paras = await self._raw.gettrpara(type=float)
        Nreal = paras[2]
        self._trigStart = Q_(paras[0], 'mm')
        self._trigStop = Q_(paras[1], 'mm')
        self._trigStep = (self._trigStop - self._trigStart) / Nreal

        return (self._trigStep, self._trigStart, self._trigStop)


if __name__ == '__main__':

    loop = asyncio.get_event_loop()

    async def run():
        transport, hydra = await loop.create_connection(Hydra, 'localhost',
                                                        4000)

        async with hydra:
            await asyncio.sleep(4)

    loop.run_until_complete(run())
