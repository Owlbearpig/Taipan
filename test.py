# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, action, traits, Scan
from dummy import DummyManipulator, DummyContinuousDataSource


class AppRoot(Scan):

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Plot",
                                 axes_labels=['Time (ps)'],
                                 data_label="Amplitude (nA)")

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
        self.title = "Dummy measurement program"
        self.manipulator = DummyManipulator()
        self.manipulator.objectName = "Dummy Manipulator"
        self.dataSource = DummyContinuousDataSource(manip=self.manipulator)
        self.dataSource.objectName = "Dummy DataSource"
        self.continuousScan = True
        self.set_trait('currentData', DataSet())

    @action("Take measurement")
    async def takeMeasurement(self):
        self.set_trait('currentData', await self.readDataSet())
