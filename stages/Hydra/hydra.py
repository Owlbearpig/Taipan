from common import Manipulator, action
import asyncio
import logging, warnings
from threading import Lock
from asyncioext import threaded_async, ensure_weakly_binding_future
import enum
import traitlets
from common import ureg, Q_

'''
0: Controler
1: Axis 1
2: Axis 2 not connected!
3: Sensor
'''

class Hydra(Manipulator):
    class StatusBits(enum.Enum):
            axisMoving = 0x1
            manualMove = 0x2
            machineError = 0x4
            emergencyStopped = 0x80
            motorPowerDisabled = 0x100
            emergencySwitchActive = 0x200
            deviceBusy = 0x400
            invalidStatus = 0x8000
    
    isMoving = traitlets.Bool(False, read_only=True).tag(name='Moving')
    isServoOn = traitlets.Bool(False, read_only=True)
    isDeviceBusy = traitlets.Bool(False, read_only=True)
    isOnTarget = traitlets.Bool(False, read_only=True)
    numberParamStack = traitlets.Int(0, read_only=True,group='Restart after Failure')
    isDebug = traitlets.Bool(True, read_only=False)
    
    def __init__(self,resource,axis=1,objectName=None,loop=None):
        super().__init__(objectName, loop)
        self.resource = resource
        self.resource.timeout = 1500
        self.resource.read_termination = '\r\n'
        #self.resource.query_delay = 0.1
        self.axis = axis
        
        self._identification = None
        self._status = 0x0
        self._isReferenced = False
        self._movementStopped = True
        self._targetReached = True
        self._isMovingFuture = asyncio.Future()
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)

        self._lock = Lock()                
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)
        
    async def __aenter__(self):
        await self.initialize()        
        await self.calibrationMove()
        return self
        
    def __del__(self):
        #logging.info('Hydra: connection closed')
        self.resource.close()

    async def __aexit__(self,*args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()
        
    async def initialize(self):
        await self.clearStack()
        self._identification = await self.query(self._buildHydraCommand('nidentify'))
        #should i always to a calibration and range measurement move?
        await self.write(self._buildHydraCommand('snv',40))

        limits=await self.query(self._buildHydraCommand('getnlimit'))
        self._hardwareMinimum = Q_(float(limits.split(' ')[0]),'mm')
        self._hardwareMaximum = Q_(float(limits.split(' ')[1]),'mm')
        self.velocity = Q_(float(await self.query(self._buildHydraCommand('gnv'))),'mm/s')

    @threaded_async
    def query(self,command):
        with self._lock:
            #print('Hydra: ' + command)
            res = self.resource.query(command)            
            #print(res)
            return res
            
    @threaded_async    
    def write(self,command):
        with self._lock:
            #print('Hydra: ' + command)
            self.resource.write(command)

    async def updateStatus(self):

        while True:
            if (self.resource is None):
                continue
            await self.singleUpdate()
            await asyncio.sleep(1)

    async def singleUpdate(self):
        self._status = int(await self.query(self._buildHydraCommand('nst')))
        pos = float(await self.query(self._buildHydraCommand('np')))
        self.set_trait('value', Q_(pos, 'mm'))
        self.set_trait('numberParamStack',int(await self.query('gsp ')))
        self.set_trait('isDeviceBusy',
                        bool(self._status & self.StatusBits.deviceBusy.value))
        self.set_trait('isOnTarget',self._targetReached)
        self.set_trait('isServoOn',
                        not bool(self._status & self.StatusBits.motorPowerDisabled.value))
        self.set_trait('isMoving',
                       bool(self._status & self.StatusBits.axisMoving.value))
        if self.isOnTarget:
            self.set_trait('status', self.Status.TargetReached)
        elif self.isMoving:
            self.set_trait('status', self.Status.Moving)
        else:
            self.set_trait('status', self.Status.Undefined)
            if self.isDebug:
                logging.info('{} in an undefined state!'.format(self))

        if not self._isMovingFuture.done() and not self.isMoving:
            self._isMovingFuture.set_result(self._movementStopped)


    def _buildHydraCommand(self,command,*args):
        if len(args)==0:
            return str(self.axis) + ' ' + command + ' '
        else:
            return ' '.join([str(x) for x in args]) + ' ' + str(self.axis) + ' ' + command + ' '

    @action('Calibrate')
    async def calibrationMove(self):
        '''
        Moves stage to lower endswitch and sets lower hardware limit to 0
        '''
        if self.isDebug:
            logging.info('Hydra: Calibration Move Triggered')
        self._movementStopped = False
        await self.write(self._buildHydraCommand('ncal'))
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture
        self._isReferenced = True
        

    @action('Auto Detect Range')
    async def rangeMove(self):
        '''Finds upper hardware limit'''
        if self.isDebug:
            logging.info('Hydra: Range Move Triggered')
        self._movementStopped = False
        await self.write(self._buildHydraCommand('nrm'))
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

    async def reference(self):
        await self.calibrationMove()
        await self.rangeMove()

    @action('Restart Axis',group='Restart after Failure')
    async def restartAxis(self):
        '''in case of emergency state, repower motor'''
        if self.isDebug:
            logging.info('Hydra: Axis Restart')
        await self.write(self._buildHydraCommand('init'))
    
    @action('Clear Stack',group='Restart after Failure')
    async def clearStack(self):
        '''in case of some not finished execution, clearing the stack is possible'''
        if self.isDebug:
            logging.info('Hydra: Command stack cleared')
        await self.write('clear ')

    # 0.75 mm buffer for acceleration and proper trigger position
    async def beginScan(self, start, stop, velocity=None):
        if self.isDebug:
            logging.info('Hydra: begin Scan called')
        start = start.to('mm')
        stop = stop.to('mm')
        velocity = velocity.to('mm/s')

        if stop > start:
            await self.moveTo(start - Q_(0.75,'mm'), velocity)
        else:
            await self.moveTo(start + Q_(0.75,'mm'), velocity)

        res = await self.configureTrigger(self._trigStep, self._trigStart, self._trigStop)
        if self.isDebug:
            logging.info('Hydra: Trigger configured: ' + 
                        'Step={:.3f~}'.format(res[0].to('fs')) + ' Start={:.3f~}'.format(res[1].to('ps')) + 
                        ' Stop={:.3f~}'.format(res[2].to('ps')))

    @action('Stop')
    def stop(self):
        self._movementStopped = True
        asyncio.ensure_future(self.write(self._buildHydraCommand('nabort')))
        if self.isDebug:
            logging.info('Hydra: Movement aborted')
        
    def setAxis(self, iaxis):
        '''
        Set the axis under control to iaxis.
            iaxis: 0 or 1
        '''
        if iaxis == 1:
            self.axis = iaxis
        else:
            self.axis = 2

    async def moveTo(self, val: float, velocity=None):
        if self.isDebug:
            logging.info('Hydra: Move To {:.3f~}'.format(val.to('mm')))
            
        if velocity is None:
            velocity = self.velocity

        await self.write(self._buildHydraCommand('snv',velocity.to('mm/s').magnitude))
        #where is the stage connected?
        
        self._movementStopped = False
        self._targetReached = False        
        await self.write(self._buildHydraCommand('nm',val.to('mm').magnitude))
        await asyncio.sleep(1.1) #hard blocking needed?
        #is using ast also an option here?
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture
        if abs(self.value.to('mm') - val.to('mm')) > Q_(1e-2,'mm'):
            #maybe print error details
            if self.isDebug:
                    l='{} Target not reached! '.format(self)
                    logging.info(l+'value: {}, target: {}'.format(self.value.to('mm'),val.to('mm')))
            self._targetReached = False
        else:
            self._targetReached = True
        return self.isOnTarget and not self._movementStopped

    #@threaded_async
    async def configureTrigger(self, step, start=None, stop=None):
        '''   if start is None or stop is None:
            raise Exception("The start and stop parameters are mandatory!")

        Note that at the time of arming, the slide or rotor position has
        to be consistent with the specified temporal trigger position
        order, i.e. the first trigger position has to be located between
        the current position and the last trigger position
'''
        step = step.to('mm').magnitude
        start = start.to('mm').magnitude
        stop = stop.to('mm').magnitude

        N = int((stop-start)/step)+1
        trigconf ='{} {} {}'.format(start,stop,N)
        
        #enable equidistant trigger mode
        
        await self.write('300 1 1 settroutpw 0 1 1 settroutdelay '\
            '1 1 1 settroutpol 3 1 settr ' + trigconf + ' 1 settrpara ' )
            # just for testing
        
#        # ask for the actually set start, stop and step parameters
        paras=await self.query('1 gettrpara')
        Nreal = float(paras.split()[2])
        self._trigStart = Q_(float(paras.split()[0]),'mm')
        self._trigStop = Q_(float(paras.split()[1]),'mm')
        self._trigStep = (self._trigStop-self._trigStart)/(Nreal)        
        return (self._trigStep,self._trigStart,self._trigStop)

#


if __name__ == '__main__':
    import visa
    rm=visa.ResourceManager('@py')
    #res=rm.list_resources()
    #print(res)
    #my_conn = rm.open_resource('TCPIP0::10.0.10.82::400::SOCKET')

    #my_conn.close()

    async def run():
        hydra_conn = rm.open_resource('TCPIP0::10.0.10.82::400::SOCKET')
        manip = Hydra(hydra_conn)
        #await manip.calibrationMove()
        #manip.restartAxis()
        #manip.initialize()
        #manip.reference()


        print(manip.isServoOn)
        await manip.moveTo(Q_(30,'mm'),Q_(10,'mm/s'))
        for i in range(3):
            await asyncio.sleep(0.5)
            print(manip.value)

        #await  manip.moveTo(20,1)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())