from traitlets import Instance, Float, Integer
from common import ComponentBase, action
from common.save import DataSaver
from common.traits import DataSet as DataSetTrait
from datasources.terak15 import TeraK15

class AppRoot(ComponentBase):

    dataSaver = Instance(DataSaver)
    terak15 = Instance(TeraK15)
    currentMeasurement = DataSetTrait().tag(name="Current measurement",
                                            data_label="Amplitude",
                                            axes_labels=["Time"])

    progress = Float(0, min=0, max=1, read_only=True).tag(name="Progress")
    nMeasurements = Integer(1, min=1).tag(name="No. of measurements", priority=99)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName="Measurement", loop=loop)
        self.title = "Taipan"

        self.dataSaver = DataSaver(objectName="Data Saver")
        self.terak15 = TeraK15(name_or_ip="192.168.134.80", objectName="TeraK15", loop=loop)

    async def __aenter__(self):
        await super().__aenter__()
        return self

    @action("Take measurements")
    async def takeMeasurements(self):
        for i in range(self.nMeasurements):
            self.set_trait("progress", i / self.nMeasurements)
            self.set_trait("currentMeasurement", await self.terak15.readDataSet())
            self.dataSaver.process(self.currentMeasurement)

        self.set_trait("progress", 1)


    async def __aexit__(self, *args):
        await super().__aexit__(*args)
