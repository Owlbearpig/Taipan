# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, action, traits, ComponentBase, Scan, ureg, Q_
from dummy import DummyManipulator, DummyContinuousDataSource


class AppRoot(Scan):

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude")

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
        self.title = "Dummy measurement program"
        manip = DummyManipulator()
        self.manipulator = manip
        self.manipulator.objectName = "Dummy Manipulator"
        self.dataSource = DummyContinuousDataSource(manip=self.manipulator)
        self.dataSource.objectName = "Dummy DataSource"
        self.continuousScan = True
        self.set_trait('currentData', DataSet())

        self.minimumValue = Q_(0, 'mm')
        self.maximumValue = Q_(1, 'mm')
        self.step = Q_(0.01, 'mm')
        self.positioningVelocity = Q_(20, 'mm/s')
        self.scanVelocity = Q_(20, 'mm/s')

    @action("Take measurement")
    async def takeMeasurement(self):
        self.set_trait('currentData', await self.readDataSet())
