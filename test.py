# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from scan import Scan
from dummy import DummyManipulator, DummySimpleDataSource,
                  DummyContinuousDataSource
import numpy as np
import asyncio

async def testRun():
    manip = DummyManipulator()
    sourceA = DummyContinuousDataSource(init = 42, count = 10)
    scan = Scan(manip, sourceA, minimumValue = 0, maximumValue = 10, step = 1)
    scan.continuousScan = True
    scanB = Scan(DummyManipulator(), scan, minimumValue = 0,
                 maximumValue = 1.5, step = 1)

    dataSet = await scanB.readDataSet()
    print(dataSet)

loop = asyncio.get_event_loop()
loop.run_until_complete(testRun())
