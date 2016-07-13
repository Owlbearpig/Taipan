# -*- coding: utf-8 -*-
"""
Created on Thu Jul  7 09:17:32 2016

@author: Arno Rehn
"""

import asyncio
from datasources import TW4B
from traitlets import Instance
from common import action
from common.save import DataSaver


class AppRoot(TW4B):

    dataSaver = Instance(DataSaver)

    def __init__(self):
        super().__init__(objectName="TeraFlash")
        self.dataSaver = DataSaver(objectName="Data Saver")

    async def __aenter__(self):
        self.start_device_discovery()
        await asyncio.sleep(1)
        await super().__aenter__()
        return self

    @action("Take measurement")
    async def takeMeasurement(self):
        data = await self.readDataSet()
        self.dataSaver.process(data)
