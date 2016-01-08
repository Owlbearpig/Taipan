# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import ComponentBase
from scan import Scan
from dummy import DummyManipulator, DummyContinuousDataSource
import asyncio


class AppRoot(ComponentBase):

    def __init__(self, eventHandler):
        self.objectName = "AppRoot"
        self.manip = DummyManipulator()
        self.source = DummyContinuousDataSource(manip=self.manip)
        self.scan = Scan(self.manip, self.source)
        self.scan.continuousScan = True
        self.eventHandler = eventHandler

    def listAttributes(self):
        return ['source', 'manip', 'scan']

    async def takeMeasurement(self):
        return await self.scan.readDataSet()


loop = asyncio.get_event_loop()
