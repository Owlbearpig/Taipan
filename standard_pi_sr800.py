# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 15:04:51 2015

@author: pumphaus
"""

from common import DataSet, action, traits, Scan, ureg, Q_
from common.save import DataSaver
from pint import Context
from stages import PI
from datasources import SR830
from traitlets import Instance
import visa

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

rm = visa.ResourceManager()


class AppRoot(Scan):

    dataSaver = Instance(DataSaver)

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude",
                                 is_power=False)

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
        self.title = "Dummy measurement program"
        self.pi_conn = PI.Connection('COM17')

        pi_stage = PI.AxisAtController(self.pi_conn)
        pi_stage.objectName = "PI C-863"
        pi_stage.setPreferredUnits(ureg.ps, ureg.ps / ureg.s)
        self.manipulator = pi_stage

        self.dataSource = SR830(rm.open_resource('GPIB0::10::INSTR'))
        self.dataSource.objectName = "SR830"

        self.continuousScan = True
        self.set_trait('currentData', DataSet())

        self.minimumValue = Q_(200, 'ps')
        self.maximumValue = Q_(320, 'ps')
        self.step = Q_(0.05, 'ps')
        self.positioningVelocity = Q_(10, 'ps/s')
        self.scanVelocity = Q_(1, 'ps/s')

        self.dataSaver = DataSaver(objectName="Data Saver")

    async def __aenter__(self):
        await super().__aenter__()

        await self.pi_conn.__aenter__()
        await self.manipulator.__aenter__()
        await self.dataSource.__aenter__()

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)

        await self.dataSource.__aexit__(*args)
        await self.manipulator.__aexit__(*args)
        await self.pi_conn.__aexit__(*args)

    @action("Take measurement")
    async def takeMeasurement(self):
        self.set_trait('currentData', await self.readDataSet())
        self.dataSaver.process(self.currentData)
