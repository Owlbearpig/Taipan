# -*- coding: utf-8 -*-
"""
Created on Mon Nov  2 08:57:30 2015

@author: Arno Rehn
"""

import visa
import interfaces.prologix_gpib
from datasources import SR830
import asyncio

rm = visa.ResourceManager('@py')

sr830 = SR830(rm.open_resource('GPIB0::10::INSTR'))
print(sr830.identification())

async def testData():
    sr830.start()
    await asyncio.sleep(5)
    sr830.stop()

    data = await sr830.readDataSet()
    print(data)

loop = asyncio.get_event_loop()
loop.run_until_complete(testData())

del interfaces.prologix_gpib.gpib_prologix_device
