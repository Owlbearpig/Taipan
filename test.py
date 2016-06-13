# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import ComponentBase, action
from scan import Scan
from dummy import DummyManipulator, DummyContinuousDataSource, DataSet
import asyncio
from traitlets import Instance, Int


def register_notification_hooks(component, objectPath=[]):
    for name, trait in component.attributes.items():
        if (isinstance(trait, Instance) and
            issubclass(trait.klass, ComponentBase)):

            cInst = getattr(component, name)
            register_notification_hooks(cInst, objectPath + [name])
        else:
            def print_change(change):
                print("Change at {}: {}".format(objectPath, change))

            component.observe(print_change, name)


class AppRoot(ComponentBase):

    foo = Int(42)
    currentData = Instance(DataSet, read_only=True)

    manip = Instance(DummyManipulator)
    source = Instance(DummyContinuousDataSource)
    scan = Instance(Scan)

    def __init__(self, loop=None):
        super().__init__(objectName="AppRoot", loop=loop)
        self.manip = DummyManipulator()
        self.source = DummyContinuousDataSource(manip=self.manip)
        self.scan = Scan(self.manip, self.source)
        self.scan.continuousScan = True
        self.set_trait('currentData', DataSet())

    @action("Take measurement")
    async def takeMeasurement(self):
        print("now acquiring!", flush=True)
        self.set_trait('currentData', await self.scan.readDataSet())
        print("finished acquiring data!", flush=True)


root = AppRoot()
register_notification_hooks(root)

root.scan.minimumValue = 0
root.scan.maximumValue = 10
root.scan.step = 1
root.scan.positioningVelocity = 100
root.scan.scanVelocity = 10

loop = asyncio.get_event_loop()
loop.run_until_complete(root.takeMeasurement())
