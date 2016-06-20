# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, action, traits, Scan
from common.fouriertransform import FourierTransform
from dummy import DummyManipulator, DummyContinuousDataSource
from traitlets import Instance


class AppRoot(Scan):

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time (ps)'],
                                 data_label="Amplitude (nA)")

    current_ft = traits.DataSet(read_only=True).tag(
                                name="Spectrum",
                                prefer_logscale=True)

    fft = Instance(FourierTransform)

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
        self.title = "Dummy measurement program"
        self.manipulator = DummyManipulator()
        self.manipulator.objectName = "Dummy Manipulator"
        self.dataSource = DummyContinuousDataSource(manip=self.manipulator)
        self.dataSource.objectName = "Dummy DataSource"
        self.continuousScan = True
        self.fft = FourierTransform(objectName="Fourier transform")
        self.set_trait('currentData', DataSet())

        self.minimumValue = 0
        self.maximumValue = 1
        self.step = 0.01
        self.positioningVelocity = 20
        self.scanVelocity = 20

    @action("Take measurement")
    async def takeMeasurement(self):
        self.set_trait('currentData', await self.readDataSet())
        self.set_trait('current_ft', self.fft.process(self.currentData))
