# -*- coding: utf-8 -*-
"""
Created on Mon Nov  9 14:56:42 2015

@author: Arno Rehn
"""

import visa
import interfaces.prologix_gpib as prologix_gpib
from serial import Serial
from datasources import SR830
import asyncio
from stages import PI

import asyncioext

prologix_gpib.gpib_prologix_device = Serial('/tmp/sr830', baudrate=115200, timeout = 0.150)

rm = visa.ResourceManager('@py')

sr830 = None
conn = None
controller = None

async def setup():
    global sr830, conn, controller

    sr830 = SR830(rm.open_resource('GPIB0::10::INSTR'))
    print(sr830.identification)

    conn = PI.Connection(baudRate = 9600)
    conn.port = '/tmp/pistage'
    conn.open()

    controller = PI.AxisAtController(conn)
    await controller.initialize()
    print("PI Controller is: %s" % controller._identification, flush=True)
    print("PI position: %s" % str(controller.value))

async def run():
    await setup()

    realVals = await controller.configureTrigger(0.1, 10, 20)
    print(realVals)

loop = asyncio.get_event_loop()
loop.run_until_complete(run())

del controller
del conn
del sr830
del prologix_gpib.gpib_prologix_device

loop.run_until_complete(asyncio.sleep(1))
