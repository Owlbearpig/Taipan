# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import ComponentBase
from scan import Scan
from dummy import DummyManipulator, DummyContinuousDataSource
from jsonrpclib.jsonrpc import _Method
import asyncio


class ClientNotifier:
    def __init__(self):
        self._clients = []

    def _clientNotify(self, methodname, params):
        print("notifying clients of {}{}".format(methodname, params or "()"))
        for client in self._clients:
            client._request_notify(methodname, params)

    def __getattr__(self, name):
        return _Method(self._clientNotify, name)


class AppRoot(ComponentBase):

    def __init__(self, client, loop=None):
        super().__init__(objectName="AppRoot", loop=loop)
        self.manip = DummyManipulator()
        self.source = DummyContinuousDataSource(manip=self.manip)
        self.scan = Scan(self.manip, self.source)
        self.scan.continuousScan = True
        self.client = client

        self._publishComponents("manip", "scan", "source")
        self._publishActions(
            (self.takeMeasurement, "Take measurement"),
        )

    async def takeMeasurement(self):
        print("now acquiring!", flush=True)
        data = await self.scan.readDataSet()
        print("finished acquiring data!", flush=True)
        return data


clients = ClientNotifier()
root = AppRoot(clients)
root.scan.minimumValue = 0
root.scan.maximumValue = 10
root.scan.step = 1
root.scan.positioningVelocity = 100
root.scan.scanVelocity = 1

loop = asyncio.get_event_loop()
loop.run_until_complete(root.takeMeasurement())
