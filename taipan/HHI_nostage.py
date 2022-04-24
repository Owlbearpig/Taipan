import traitlets
import asyncio
from traitlets import Instance
from common import ComponentBase, action
from common.save import DataSaver
from common.traits import DataSet as DataSetTrait
from datasources.tw4b import TW4B

class AppRoot(ComponentBase):

    dataSaver = Instance(DataSaver)
    tw4b = Instance(TW4B)
    currentMeasurement = DataSetTrait().tag(name="Current measurement",
                                            data_label="Amplitude",
                                            axes_labels=["Time"])

    progress = traitlets.Float(0, min=0, max=1, read_only=True).tag(name="Progress")
    traitlets.Int(1, min=1).tag(name="No. of measurements", priority=99)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName="Measurement", loop=loop)
        self.title = "Taipan - HHI"

        self.dataSaver = DataSaver(objectName="Data Saver")
        self.tw4b = TW4B(objectName="TW4B", loop=loop)

        self.nMeasurements = traitlets.Int(1, min=1).tag(name="No. of measurements", priority=99)


    async def __aenter__(self):
        self.tw4b.start_device_discovery()
        await asyncio.sleep(2)
        await super().__aenter__()
        return self

    @action("Take measurements")
    async def takeMeasurements(self):
        for i in range(self.nMeasurements):
            self.set_trait('progress', i / self.nMeasurements)
            self.set_trait("currentMeasurement", await self.tw4b.readDataSet())
            self.dataSaver.process(self.currentMeasurement)
