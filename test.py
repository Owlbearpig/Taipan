# -*- coding: utf-8 -*-
"""
Created on Mon Jul  4 16:01:45 2016

@author: Arno Rehn
"""

from common import DataSet, action, traits, Scan, ureg, Q_
from pint import Context
from dummy import DummyManipulator, DummyContinuousDataSource
from traitlets import Int, Instance
from common.save import DataSaver

# Create and enable a THz-TDS context where we can convert times to lengths
# and vice-versa
thz_context = Context('terahertz')

thz_context.add_transformation('[time]', '[length]',
                               lambda ureg, x: ureg.speed_of_light * x / 2)
thz_context.add_transformation('[length]', '[time]',
                               lambda ureg, x: 2 * x / ureg.speed_of_light)

thz_context.add_transformation('', '[length]/[time]',
                               lambda ureg, x: ureg.speed_of_light * x / 2)
thz_context.add_transformation('[length]/[time]', '',
                               lambda ureg, x: 2 * x / ureg.speed_of_light)

ureg.add_context(thz_context)
ureg.enable_contexts('terahertz')


class AppRoot(Scan):

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude",
                                 is_power=False)

    dataSaver = Instance(DataSaver)

    nMeasurements = Int(1, min=1).tag(name="No. of measurements", priority=99)

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
        self.title = "Dummy measurement program"

        self.dataSaver = DataSaver(objectName="Data saver")

        pi_stage = DummyManipulator()
        pi_stage.objectName = "Dummy Manip"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        self.manipulator = pi_stage
        self.dataSource = DummyContinuousDataSource(self.manipulator)
        self.dataSource.objectName = "Dummy DataSource"
        self.continuousScan = True
        self.set_trait('currentData', DataSet())

        self.dataSaver.registerManipulator(pi_stage, "PI")

        self.minimumValue = Q_(200, 'ps')
        self.maximumValue = Q_(240, 'ps')
        self.step = Q_(0.01, 'ps')
        self.positioningVelocity = Q_(100, 'ps/s')
        self.scanVelocity = Q_(100, 'ps/s')

        self.addDataSetReadyCallback(self.dataSaver.process)

    @action("Take measurement")
    async def takeMeasurement(self):
        for x in range(self.nMeasurements):
            self.set_trait('currentData', await self.readDataSet())
