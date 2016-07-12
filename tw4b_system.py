# -*- coding: utf-8 -*-
"""
Created on Thu Jul  7 09:17:32 2016

@author: Arno Rehn
"""

from datasources import TW4B
from traitlets import Instance
from common import action
from common.save import DataSaver


class AppRoot(TW4B):

    dataSaver = Instance(DataSaver)

    def __init__(self):
        super().__init__('169.254.4.42', objectName="TeraFlash")
        self.dataSaver = DataSaver(objectName="Data Saver")

    @action("Take measurement")
    async def takeMeasurement(self):
        data = await self.readDataSet()
        self.dataSaver.process(data)
