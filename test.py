# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from scan import Scan
from dummy import DummyManipulator, DummySimpleDataSource, \
                  DummyContinuousDataSource
import numpy as np
import asyncio
from stages import PI
import time
from asyncioext import threaded_async

async def testRun():
    manip = DummyManipulator()
    sourceA = DummyContinuousDataSource(init = 42, count = 10)
    scan = Scan(manip, sourceA, minimumValue = 0, maximumValue = 10, step = 1)
    scan.continuousScan = True
    scanB = Scan(DummyManipulator(), scan, minimumValue = 0,
                 maximumValue = 1.5, step = 1)

    dataSet = await scanB.readDataSet()
    print(dataSet)

async def testComm():
    conn = PI.Connection()
    conn.port = '/tmp/pistage'
    conn.open()
    controller = PI.AxisAtController(conn)
    await controller.initialize()
    print(controller._identification)
    print(controller.value)
    success = await controller.reference()
    print("Reference: %s" % str(success), flush=True)
    print("Velocity: %s" % controller._velocity, flush=True)
    success = await controller.moveTo(34.3)
    print("Moving: %s, now at %f" % (str(success), controller.value), flush=True)

async def doSomething():
    await asyncio.sleep(0.5)
    print("done something!", flush=True)

@threaded_async
def testExecutor(s):
    time.sleep(2)
    print("hello" + s, flush=True)

async def wait_secs(n):
    await asyncio.sleep(n)

loop = asyncio.get_event_loop()
asyncio.ensure_future(doSomething())
asyncio.ensure_future(testExecutor(" WORLD!"))
loop.run_until_complete(wait_secs(3))
