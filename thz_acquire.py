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

prologix_gpib.gpib_prologix_device = Serial('/tmp/sr830', baudrate=115200, timeout = 0.150)

rm = visa.ResourceManager('@py')

sr830 = None
conn = None
controller = None

async def setup():
    global sr830, conn, controller

    sr830 = SR830(rm.open_resource('GPIB0::10::INSTR'))

    conn = PI.Connection()
    conn.port = '/tmp/pistage'
    conn.open()

    controller = PI.AxisAtController(conn)
    await controller.initialize()
    print("PI Controller is: %s" % controller._identification)
    if not controller.isReferenced:
        await controller.reference()

async def run():
    await setup()

loop = asyncio.get_event_loop()
loop.run_until_complete(run())
