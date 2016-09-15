# -*- coding: utf-8 -*-
"""
Created on Sun May 29 21:15:46 2016

@author: Terahertz
"""

from common import Manipulator, action, ureg, Q_
import asyncio
from asyncioext import threaded_async,ensure_weakly_binding_future
import enum
import traitlets

class IAIStage(Manipulator):

    class OutBits(enum.Enum):
        pos1 = 0x1
        pos2 = 0x2
        pos3 = 0x4
        pos4 = 0x8
        moveComplete = 0x10
        homeComplete = 0x20
        zone = 0x40
        alarm = 0x80

    class StatusBits(enum.Enum):
        powerStatus = 0x1 #0 power off
        servoStatus = 0x2 # 0 servo off
        runStatus = 0x4  #0 not ready to move
        homeStatus = 0x8 #0 Home not complete, 1 Home Complete
        commandRefusal = 0x80 #0 Ok, 1 Refused

    Alarm={
        int('00',16) : 'noAlarm',
        int('5A',16) : 'BufferOverflow',
        int('5B',16) : 'BufferFrameError',
        int('5C',16) : 'HeaderAbnormalCharacter',
        int('5D',16) : 'DelimiterAbnormalCharacter',
        int('5F',16) : 'BCCError',
        int('61',16) : 'ReceivedBadCharacter',
        int('62',16) : 'IncorrectOperand',
        int('63',16) : 'IncorrectOperand',
        int('64',16) : 'IncorrectOperand',
        int('70',16) : 'Tried to move while run status was off',
        int('74',16) : 'Tried to move during motor commutation',
        int('75',16) : 'Tried to move while homing',
        int('B1',16) : 'Position data error',
        int('B8',16) : 'Motor commutation error',
        int('B9',16) : 'Motor Commutation error',
        int('BB',16) : 'Bad encoder feedback while homing',
        int('C0',16) : 'Excess speed',
        int('C1',16) : 'Servo error',
        int('C8',16) : 'Excess current',
        int('D0',16) : 'Excess main power voltage',
        int('D1',16) : 'Excess main power over-regeneration',
        int('D8',16) : 'Deviation error',
        int('E0',16) : 'Overload',
        int('E8',16) : 'Encoder disconnect',
        int('ED',16) : 'Encoder error',
        }
        #more to come ?really the best way to do this?

    def __init__(self,resource,axis=0,objectName=None,loop=None):
        super().__init__(objectName, loop)
        self.resource = resource
        self.resource.timeout = 1500
        self.resource.read_termination = chr(0x03)
        self._identification = None
        #self._status = 0x0

        self._movementStopped = True
        self._targetReached = True

        self._isMovingFuture = asyncio.Future()
        self.setPreferredUnits(ureg.mm, ureg.mm / ureg.s)
        self.axis = axis
        self.velocity = Q_(5.0,'mm/s')
        self._position = '00000000'
        self._leadpitch = self._getLeadPitch()
        ensure_weakly_binding_future(self.updateStatus)
  #      self.setVelocity(self.velocity)

    async def updateStatus(self):
        while True:
            if (self.resource is None):
                continue
            await self.singleUpdate()
            await asyncio.sleep(0.5)


    isReadyToMove = traitlets.Bool(False, read_only=True)
    isServoOn = traitlets.Bool(False, read_only=True)
    isReferenced = traitlets.Bool(False, read_only=True)
    isPowerOn = traitlets.Bool(False, read_only = True)
    isAlarmState = traitlets.Bool(False, read_only=True)
    isOnTarget = traitlets.Bool(True, read_only=True)
    isMoving = traitlets.Bool(True, read_only=False)
    statusMessage = traitlets.Unicode('',read_only=True)

    async def singleUpdate(self):

        self.send(str(self.axis) + 'n0000000000') # any send command updates
        self._position = self.send(str(self.axis) + 'R4000074000')[4:]
        self.set_trait('isReadyToMove',
                       bool(self._status & self.StatusBits.runStatus.value))
        self.set_trait('isServoOn',
                       bool(self._status & self.StatusBits.servoStatus.value))
        self.set_trait('isReferenced',
                       bool(self._status & self.StatusBits.homeStatus.value))
        self.set_trait('isPowerOn',
                       bool(self._status & self.StatusBits.powerStatus.value))

        self.set_trait('isMoving',
                       not bool(self._outs & self.OutBits.moveComplete.value))
        self.set_trait('isAlarmState', bool(self._alarm != 0))
        self.set_trait('statusMessage',IAIStage.Alarm.get(self._alarm))
        self.set_trait('isOnTarget', self._targetReached)
        self.set_trait('value',self._getValue())

        if self.isOnTarget:
            self.set_trait('status', self.Status.TargetReached)
        elif True:
            self.set_trait('status', self.Status.Moving)
        else:
            self.set_trait('status', self.Status.Undefined)

        if not self._isMovingFuture.done() and not self.isMoving:
            self._isMovingFuture.set_result(self._movementStopped)

#        self.printStatus()

    @action('Home Stage')
    def reference(self,motorend=True):
        command=str(self.axis) + 'o'
        if motorend:
            command += '07'
        else:
            command += '08'

        command += '00000000'

        self.send(command)

    @action('Enable Servo')
    def enableServo(self):
        if not self.isServoOn:
            self.send(str(self.axis) + 'q1000000000')
        else:
            print('servo was already on')

    @action('Disable Servo')
    def disableServo(self):
        if self.isServoOn:
            self.send(str(self.axis) + 'q0000000000')
        else:
            print('Servo was already off')

    def setVelocity(self,velocity = Q_(10,'mm/s'), acceleration = 0.1):
        velocity = hex(int(velocity.to('mm/s').magnitude * 300/self._leadpitch))[2:].upper()
        if len(velocity)>4:
            print('error: velocity too high')
            velocity = 'FFFF'
        else:
            velocity = '0' * (4-len(velocity)) + velocity

        acceleration = hex(int(acceleration * 5883.99/self._leadpitch))[2:].upper()
        if len(acceleration)>4:
            print('Error: Acceleration too high')
            acceleration = 'FFFF'
        else:
            acceleration ='0' * (4-len(acceleration)) + acceleration
        sendstr = str(self.axis) + 'v2' + velocity + acceleration + '0'
        self.send(sendstr)

    def _getValue(self):
        return Q_(self._convertPositionTomm(self._position),'mm')

    def getVelocity(self):
        #seems not to work
        #vel = self.send(str(self.axis) +  'R4000074010')[4:]
        vel = self.send(str(self.axis) +  'R4000004040')[4:]
        vel = Q_(int(vel,16)/300.0*self._leadpitch,'mm/s')
        return vel


    def _getLeadPitch(self):
        res = self.send(str(self.axis) +'R4000000170')
        sizes=[2.5,3.0,4.0,5.0,6.0,8.0,10.0,12.0,16.0,20.0]
        try:
            return sizes[int(res[-1])]
        except:
            print('Error: Lead pitch size not in list')
            return 0

    @action('Stop Stage')
    def stop(self):
        self._movementStopped = True
        self.send(str(self.axis) + 'd0000000000')

    @action('Reset Stage')
    def resetStage(self):
        self.send(str(self.axis) +'r0300000000')

    async def moveTo(self, val: float, velocity=None):
        #seems not to be possible for not homed stages?
        if velocity is not None:
            self.setVelocity(velocity)

        posstr = self._convertPositionToHex(val)

        self._movementStopped = False
        self._isMovingFuture = asyncio.Future()
        self.send(str(self.axis) + 'a' + posstr + '00')
        await self._isMovingFuture

        if abs(self.value.to('mm') - val.to('mm')) > Q_(0.1,'mm'):
            #maybe print error details
            self._targetReached = False
        else:
            self._targetReached = True

        return self.isOnTarget and not self._movementStopped

    def _parseStatusString(self,statusstring):
            #0'U' answer string
        #1'0' axis number
        #2 'n' status inqiry result
        #3+4 '07' hex value corresponding to status
        #5+6 '00' hex value corresponding to Alarm
        #7+8 '40' hex value corresponding to IN
        #9+10 '90' hex value corresponding to OUT
        self._status=int(statusstring[3:5],16)
        self._alarm=int(statusstring[5:7],16)
        #ins = int(statusstring[7:9],16) # currently unused
        self._outs = int(statusstring[9:11],16)

    def _convertPositionTomm(self,positionhexstr):
        #not tested!
        value = int(positionhexstr,16)*self._leadpitch/800.0
        if positionhexstr[0] == 'F':
            return -(int('FFFFFFFF',16)*self._leadpitch/800.0 - value)
        else:
            return value

    def _convertPositionToHex(self,position):

        position = 800.0/self._leadpitch * position.to('mm').magnitude

        #if (self._position[0] == 'F' and positionmm >= 0) or \
        #(self._position[0] == '0' and positionmm < 0):
        if position < 0:
            position = int('FFFFFFFF',16) + position

        position = hex(int(position))[2:].upper()
        position = '0' * (8-len(position)) + position

        return position

    def _calculateChecksum(self,command):

        a=2**16 - sum(map(ord,command))
        a=hex(a & 255)
        BCC = a.split('x')[1]

        BCC=BCC.upper()
        if len(BCC)==1:
            BCC = '0' + BCC
        return BCC

    def send(self,command):
        command += self._calculateChecksum(command)

        result = self.resource.query('\x02' + command + '\x03')
        result = result[1:]
        if command[1].islower():
            self._parseStatusString(result)

        if int(self._calculateChecksum(result[:-2]),16) != int(result[-2:],16):
            print('Checksum Error',result[-2:],self._calculateChecksum(result[:-2]))

        if int(result[1],16) != self.axis:
            print('Wrong Axis')

        return result[:-2]

    def printStatus(self):

        print('Ready to Move',self.isReadyToMove)
        print('Servo On', self.isServoOn)
        print('Referenced',self.isReferenced)
        print('PowerOn',self.isPowerOn)
        print('Alarm State',self.isAlarmState)
        print('OnTarget',self.isOnTarget)
        print('Status message',self.statusMessage)
        print('Position',self.value)
        print('velocity',self.velocity)
        print('----------------------------------------')

if __name__ == '__main__':

    async def run():
        import visa
        rm=visa.ResourceManager()
        resources = rm.list_resources_info()
        port = '2'
        resourcename = None

        #find com2 port
        for val in resources.values():
            if val.alias == 'COM' + port:
                resourcename = val.resource_name

        if resourcename != None:
            print(resourcename)

        else:
            print('Resource not found')

        res = rm.open_resource(resourcename)
        res.baud_rate = 38400
        myStage = IAIStage(res)
        await asyncio.sleep(1)
        myStage.setVelocity(Q_(1,'mm/s'))
        #myStage.printStatus()
        await  myStage.moveTo(Q_(-20,'mm'))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())