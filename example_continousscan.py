from pint import Context
from common.units import ureg
from common import action
from traitlets import Instance
from common.components import ComponentBase
from common.traits import DataSet as DataSetTrait
from dummy import DummyManipulator, DummyContinuousDataSource

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


class AppRoot(ComponentBase):
    currentMeasurement = DataSetTrait().tag(name="Current measurement",
                                            data_label="Amplitude",
                                            axes_labels=["Time"])

    manipulator = Instance(DummyManipulator)
    dataSource = Instance(DummyContinuousDataSource)

    def __init__(self, loop=None):
        super().__init__(objectName=": )", loop=loop)
        self.manipulator = DummyManipulator()
        self.manipulator.objectName = "Stage"
        self.dataSource = DummyContinuousDataSource(self.manipulator)

    async def __aenter__(self):
        await super().__aenter__()
        return self

    @action("Start continuous datasource")
    async def takeMeasurements(self):
        await self.dataSource.update_live_data()
