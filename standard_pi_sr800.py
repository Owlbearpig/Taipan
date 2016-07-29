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
from traitlets import Int, Instance
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


class BaseTHzScan(Scan):

    dataSaver = Instance(DataSaver)

    currentData = traits.DataSet(read_only=True).tag(
                                 name="Time domain",
                                 axes_labels=['Time'],
                                 data_label="Amplitude",
                                 is_power=False)

    nMeasurements = Int(1, min=1).tag(name="No. of measurements", priority=99)

    def __init__(self, loop=None):
        super().__init__(objectName="Scan", loop=loop)
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
        self.addDataSetReadyCallback(self.dataSaver.process)

    async def __aenter__(self):
        await self.pi_conn.__aenter__()
        await self.manipulator.__aenter__()
        await self.dataSource.__aenter__()

        return self

    async def __aexit__(self, *args):
        await self.dataSource.__aexit__(*args)
        await self.manipulator.__aexit__(*args)
        await self.pi_conn.__aexit__(*args)

    @action("Take measurements")
    async def takeMeasurements(self):
        for x in range(self.nMeasurements):
            self.set_trait('currentData', await self.readDataSet())


class AppRoot(BaseTHzScan):
    pass
