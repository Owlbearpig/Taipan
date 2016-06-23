# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, action, traits, Scan, ureg, Q_
from dummy import DummyManipulator, DummyContinuousDataSource
from pint import Context

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
                                 is_power=True)

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
        self.title = "Dummy measurement program"
        manip = DummyManipulator()
        manip.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        self.manipulator = manip
        self.manipulator.objectName = "Dummy Manipulator"
        self.dataSource = DummyContinuousDataSource(manip=self.manipulator)
        self.dataSource.objectName = "Dummy DataSource"
        self.continuousScan = True
        self.set_trait('currentData', DataSet())

        self.minimumValue = Q_(0, 'ps')
        self.maximumValue = Q_(10, 'ps')
        self.step = Q_(0.01, 'ps')
        self.positioningVelocity = Q_(20, 'ps/s')
        self.scanVelocity = Q_(20, 'ps/s')

    @action("Take measurement")
    async def takeMeasurement(self):
        self.set_trait('currentData', await self.readDataSet())
