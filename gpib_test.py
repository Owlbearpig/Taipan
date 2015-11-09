# -*- coding: utf-8 -*-
"""
Created on Mon Nov  2 08:57:30 2015

@author: Arno Rehn
"""

import visa
import interfaces.prologix_gpib as prologix_gpib
from serial import Serial
from datasources import SR830
import asyncio

prologix_gpib.gpib_prologix_device = Serial('/tmp/sr830', baudrate=115200, timeout = 0.150)

rm = visa.ResourceManager('@py')

sr830 = SR830(rm.open_resource('GPIB0::10::INSTR'))
print(sr830.identification())

async def testData():
    sr830.setSampleRate(SR830.SampleRate.Rate_4_Hz)
    sampleRate = await sr830.getSampleRate()
    print("sample rate set to " + str(sampleRate))
    sr830.start()
    await asyncio.sleep(1)
    sr830.stop()

    data = await sr830.readDataSet()
    print(data)

loop = asyncio.get_event_loop()
loop.run_until_complete(testData())

del prologix_gpib.gpib_prologix_device
