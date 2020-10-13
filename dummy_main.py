from pint import Context
from common.units import Q_, ureg
from common import Scan
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


class AppRoot(Scan):
    def __init__(self, loop=None):
        super().__init__(objectName=": )", loop=loop)
        self.manipulator = DummyManipulator()
        self.manipulator.objectName = "Stage"
        self.dataSource = DummyContinuousDataSource(self.manipulator)

    async def __aenter__(self):
        await super().__aenter__()
        return self
