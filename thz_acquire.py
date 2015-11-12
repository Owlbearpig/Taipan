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
from scan import Scan

import matplotlib
matplotlib.use('Qt4Agg')
import matplotlib.pyplot as plt

prologix_gpib.gpib_prologix_device = Serial('/tmp/sr830', baudrate=115200, timeout = 0.15)

rm = visa.ResourceManager('@py')

sr830 = None
conn = None
controller = None

async def setup():
    global sr830, conn, controller

    sr830 = SR830(rm.open_resource('GPIB0::10::INSTR'))
    print(sr830.identification)
    sr830.setSampleRate(SR830.SampleRate.Trigger)
    print(await sr830.getSampleRate())

    conn = PI.Connection(baudRate = 9600)
    conn.port = '/tmp/pistage'
    conn.open()

    controller = PI.AxisAtController(conn)
    await controller.initialize()
    print("PI Controller is: %s" % controller._identification, flush=True)

async def printStatus():
    while True:
        print("PI position: %s" % str(controller.value))
        await asyncio.sleep(1)

async def run():
    await setup()

    def ps2mm(ps):
        c0 = 299792458.0
        return c0 * ps * 1e-12 * 1e3 / 2

    def mm2ps(mm):
        c0 = 299792458.0
        return 2 * mm / (c0 * 1e-12 * 1e3)

    scan = Scan(manipulator = controller, dataSource = sr830)

    scan.continuousScan = True
    scan.minimumValue = ps2mm(270)
    scan.maximumValue = ps2mm(310)
    scan.step = ps2mm(0.1)
    scan.positioningVelocity = 5
    scan.scanVelocity = ps2mm(2)
    scan.retractAtEnd = True

    asyncio.ensure_future(printStatus())

    data = await scan.readDataSet()

    await asyncio.sleep(2)

    plt.plot(mm2ps(data.axes[0]), data.data)
    plt.show(block=True)

loop = asyncio.get_event_loop()
loop.run_until_complete(run())
