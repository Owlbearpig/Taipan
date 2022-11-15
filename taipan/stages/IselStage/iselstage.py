# -*- coding: utf-8 -*-
"""
Created on Fri Aug 12 22:01:57 2016

@author: dave
"""

# -*- coding: utf-8 -*-
"""
Created on Sun May 29 21:15:46 2016

@author: Terahertz
"""

from common import Manipulator, action, Q_, ureg
from common.traits import Quantity
import asyncio
import ctypes
import enum
import traitlets
import logging
from taipan.asyncioext import ensure_weakly_binding_future
import os

def _getISELLibrarypath():
    bp = os.path.dirname(__file__)
    if os.name == 'nt':
        fp = bp + '\stagedriver.dll'
    elif os.name == 'posix':
        fp = bp + '/libstagedriver.so'
    return fp
    
class IselStage(Manipulator):
    class HomingTarget(enum.Enum):
        NegativeEndswitch = 17
        PositiveEndswitch = 18

    class OperationMode(enum.Enum):
        DriveFree = -3
        RevolutionControlAnalog = -2
        CurrentControlAnalog = -1
        ProfilePositionMode = 1
        ProfileVelocityMode = 2
        HomingMode = 6
        InterpolatedPositionMode = 7

    class DigitalInputFlags(enum.Enum):
        DI_NegativeEndswitch = 0x1
        DI_PositiveEndswitch = 0x2
        DI_ReferenceSwitch = 0x4
        DI_EnablingSignal = 0x8

    class PolarityFlag(enum.Enum):
        PositivePolarity = 0x00
        NegativePolarity = 0xC0

    class StatusFlag(enum.Enum):
        HomingComplete = (1 << 12)
        HomingError = (1 << 13)
        HomingMask = HomingComplete | HomingError

    StatusWordStateMachineMask = 0x6F

    cdll = ctypes.CDLL(_getISELLibrarypath())
   
    statusWord = traitlets.Unicode('', read_only=True)
    statusWord.tag(name = 'Status Word', group = 'Status Reporting')

    fault = traitlets.Unicode('No Fault',read_only=True)
    fault.tag(name = 'Current Fault', group = 'Status Reporting')

    isMoving = traitlets.Bool(False, read_only=True)
    isMoving.tag(name="moving", group= "Status Reporting")
    isOnTarget = traitlets.Bool(True, read_only=True)
    isOnTarget.tag(name="on Target", group = "Status Reporting")

    homingComplete = traitlets.Bool(True, read_only=True)
    homingComplete.tag(name="Homing complete", group="Home")
    homingError = traitlets.Bool(False, read_only=True)
    homingError.tag(name="Homing Error", group="Home")
    homeTarget = traitlets.Enum(HomingTarget,HomingTarget.NegativeEndswitch)
    homeTarget.tag(name="Home target", group="Home")

    endswitchesBridged = traitlets.Bool(False, read_only=False)
    endswitchesBridged.tag(name = "Endswitches bridged", group = "Switches")
    negativeEndswitchEnabled = traitlets.Bool(False, read_only=True)
    negativeEndswitchEnabled.tag(name= "Negative endswitch enabled", group = "Switches")
    positiveEndswitchEnabled = traitlets.Bool(False, read_only=True)
    positiveEndswitchEnabled.tag(name = "Positive endswitch enabled", group = "Switches")
    enablingSignalActivated = traitlets.Bool(False, read_only=True)
    enablingSignalActivated.tag(name = "Ready to Move", group = "Status Reporting")
    referenceSwitchActivated = traitlets.Bool(False, read_only=True)
    referenceSwitchActivated.tag(name = "Reference Switch Activated", group = "Switches")
    
    polarity = traitlets.Enum(PolarityFlag,
                    PolarityFlag.PositivePolarity)
    polarity.tag(name="Direction")

    maxVelocity = Quantity(Q_(0,'mm/s'),read_only=False) 
    acceleration = Quantity(Q_(0,'mm/s**2'), read_only=False)

    def __init__(self,comport ,baudrate = 57600,objectName=None,loop=None):
        super().__init__(objectName, loop)
        self.handle = IselStage.cdll.stagedriver_init() # Init
        self.comport = comport
        IselStage.cdll.stagedriver_open(self.handle, comport.encode('utf-8'),
                                     ctypes.c_int(baudrate))

        self._isOpen = bool(IselStage.cdll.stagedriver_is_open(self.handle))
        if self._isOpen == 0:
            raise Exception('Failed to open Isel Stage at comport : ' + 
                    comport)
            return 0
        #make sure the endswitches are enabled upon init
        self.bridgeEndswitches(False)
        self.getVelocity()
        self._isMovingFuture = asyncio.Future()
        self._isMovingFuture.set_result(None)
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s) 

    async def __aenter__(self):
        await self.singleUpdate()
        self.getMaxVelocity()
        self.observe(self.setMaxVelocity,'maxVelocity')
        self.getAcceleration()
        self.observe(self.setAcceleration,'acceleration')
        #await self.enableOperation()
        self._updateFuture = ensure_weakly_binding_future(self.updateStatus)
        return self

    @action('Home',group='Home')
    async def homeStage(self,target=None,homeOffset=0):
        if target is None:
            target=self.homeTarget
        self._movementStopped = False
        IselStage.cdll.stagedriver_home(self.handle,target.value, homeOffset)
        self.set_trait('homeTarget',target)
        if self._isMovingFuture.done():
            self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture
        await self.enableOperation() 
        #better to use them ? 
        #STAGEDRIVER_EXPORT int stagedriver_homing_complete(StageDriver *sd);
        #STAGEDRIVER_EXPORT unsigned int stagedriver_homing_status(StageDriver *sd);

    @action("Enable Operation")
    async def enableOperation(self,mode=OperationMode.ProfilePositionMode):
        #maybe we want to make the other options available in the GUI, by using a enumTrait
        IselStage.cdll.stagedriver_switch_to_operation_enable(self.handle, mode.value)
        if not self.enablingSignalActivated:
            logging.info('Please press the Power Button!')
        timeout = 10
        t=0
        while t<timeout:
            asyncio.sleep(2)
            if not self.enablingSignalActivated:
                logging.info('Please press the Power Button!')
            t+=2
        if not self.enablingSignalActivated:
            logging.info('Power on the stage failed')

    def getVelocity(self):
        vel = IselStage.cdll.stagedriver_profile_velocity(self.handle)
        self.velocity = Q_(vel, 'microm/s')

    def setVelocity(self, val):
        vel = int(val.to('microm/s').magnitude)
        IselStage.cdll.stagedriver_set_profile_velocity(self.handle,vel)

    def getMaxVelocity(self):
        vel = IselStage.cdll.stagedriver_max_profile_velocity(self.handle)
        self.set_trait('maxVelocity',Q_(vel,'microm/s').to('mm/s'))
        return self.maxVelocity
    
    def setMaxVelocity(self,vel):
        if isinstance(vel,dict):
            vel=vel['new']
        self.set_trait('maxVelocity',vel)    
        vel = int(vel.to('microm/s').magnitude)
        IselStage.cdll.stagedriver_set_max_profile_velocity(self.handle,vel)

    def getAcceleration(self):
        acc = IselStage.cdll.stagedriver_profile_acceleration(self.handle)
        acc = Q_(acc,'microm/s**2')
        self.set_trait('acceleration',acc.to('mm/s**2'))
        return self.acceleration

    def setAcceleration(self,val):
        if isinstance(val,dict):
            val=val['new']
        self.set_trait('acceleration',val)
        acc = int(val.to('microm/s**2').magnitude)
        IselStage.cdll.stagedriver_set_profile_acceleration(self.handle,acc)

    async def updateStatus(self):
        while True:
            if (not self._isOpen):
                continue
            await self.singleUpdate()
            await asyncio.sleep(1)

    async def singleUpdate(self):
        val = IselStage.cdll.stagedriver_current_position(self.handle)
        self.set_trait('value',Q_(val,'microm'))

        self._updateDigitalInputFlags()
        self._updateStatusWord()
        self._updateErrorByte()
       
        hm = bool(IselStage.cdll.stagedriver_homing_complete(self.handle))
        tr = bool(IselStage.cdll.stagedriver_target_reached(self.handle))
        mv = bool(IselStage.cdll.stagedriver_movement_active(self.handle))
        self.set_trait('homingComplete',hm)
        self.set_trait('isOnTarget', tr)
        self.set_trait('isMoving', mv)
        
        if not self.isMoving:
            self.set_trait('status', self.Status.Idle)
            if not self._isMovingFuture.done():
                self._isMovingFuture.set_result(None)
        else:
            self.set_trait('status', self.Status.Moving)

        self._isOpen = bool(IselStage.cdll.stagedriver_is_open(self.handle))
        if not self._isOpen:
            logging.info('Connection To IselStage at ' + self.comport + ' Lost')

    def _updateDigitalInputFlags(self):
        ds = IselStage.cdll.stagedriver_digital_inputs(self.handle)
        self.set_trait('negativeEndswitchEnabled',
            bool(IselStage.DigitalInputFlags.DI_NegativeEndswitch.value & ds))
        self.set_trait('positiveEndswitchEnabled',
            bool(IselStage.DigitalInputFlags.DI_PositiveEndswitch.value & ds))
        self.set_trait('enablingSignalActivated',
            bool(IselStage.DigitalInputFlags.DI_EnablingSignal.value & ds))
        self.set_trait('referenceSwitchActivated', 
            bool(IselStage.DigitalInputFlags.DI_ReferenceSwitch.value & ds))

    def _updateStatusWord(self):
        sw = IselStage.cdll.stagedriver_status_word(self.handle)
        unmasked = sw & IselStage.StatusWordStateMachineMask
        if unmasked == 0x20:
            self.set_trait('statusWord', "Not Ready To Switch On")
        elif unmasked == 0x60:
            self.set_trait('statusWord', "Switch On Disabled")
        elif unmasked == 0x21:
            self.set_trait('statusWord', "Ready To Switch On")
        elif unmasked == 0x23:
            self.set_trait('statusWord', "Switched On")
        elif unmasked ==0x27:
            self.set_trait('statusWord', "Operation Enable")
        elif unmasked == 0x07:
            self.set_trait('statusWord', "Quick Stop Active")
        elif unmasked == 0x0F:
            self.set_trait('statusWord', "Fault Reaction Active")
        elif unmasked == 0x2F:
            self.set_trait('statusWord', "Fault")

    def _updateCurrentError(self):
        cE = IselStage.cdll.stagedriver_current_error(self.handle)
        self.set_trait('fault',str(cE))

    def _updateErrorByte(self):
        eB = IselStage.cdll.stagedriver_error_byte(self.handle)

    async def __aexit__(self,*args):
        await super().__aexit__(*args)
        self._updateFuture.cancel()
        IselStage.cdll.stagedriver_close(self.handle)
        IselStage.cdll.stagedriver_destroy(self.handle)

    async def moveTo(self, val: float, velocity=None):
        if velocity is None:
            velocity = self.velocity

        self.setVelocity(velocity)
        self._movementStopped = False
        val = int(val.to('microm').magnitude)
        IselStage.cdll.stagedriver_stop(self.handle)
        IselStage.cdll.stagedriver_stop_background_actions(self.handle)
        IselStage.cdll.stagedriver_set_target_position(self.handle,ctypes.c_int(val))
        IselStage.cdll.stagedriver_start(self.handle)
        self._isMovingFuture = asyncio.Future()
        await self._isMovingFuture

    @traitlets.observe('polarity')
    def setPolarity(self,pol):
        if isinstance(pol,dict):
            pol=pol['new']
        IselStage.cdll.stagedriver_set_polarity(self.handle,pol.value)
        self.set_trait("polarity",pol)

    def getPolarity(self):
        pol = IselStage.cdll.stagedriver_polarity(self.handle)
        if pol == IselStage.Polarity.PositivePolarity.value:
            self.set_trait("polarity",IselStage.Polarity.PositivePolarity)
        else:
            self.set_trait("polarity",IselStage.Polarity.NegativePolarity)

    @traitlets.observe('endswitchesBridged')
    def bridgeEndswitches(self, val: bool):
        if isinstance(val,dict):
            val = val['new']
        IselStage.cdll.stagedriver_set_endswitch_bridge(self.handle, int(val))
        bridged = bool(IselStage.cdll.stagedriver_endswitch_bridged(self.handle))
        if bridged:
            logging.info("Take care, endswitches bridged")
        self.set_trait('endswitchesBridged',bridged)

    @action("Set Zero",group='Home')
    def setZero(self):
        IselStage.cdll.stagedriver_set_zero(self.handle)

    @action("Complete Reset",group='Status Reporting')
    def completeReset(self):
        IselStage.cdll.stagedriver_reset(self.handle)

    @action("Fault Reset",group='Status Reporting')
    def faultReset(self):
        IselStage.cdll.stagedriver_fault_reset(self.handle)

    @action("Stop")
    def stop(self):
        IselStage.cdll.stagedriver_stop(self.handle)
        IselStage.cdll.stagedriver_stop_background_actions(self.handle)
        self._isMovingFuture.cancel()

if __name__ == '__main__':

    async def run():
        pass
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
