from common import DataSet, DataSource, Q_, action
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Bool


class MultiDataSource(DataSource):
    currentData = DataSetTrait().tag(name="Live data",
                                     data_label="Amplitude",
                                     axes_labels=["Time"],
                                     is_multisource_plot=True)

    _dataSources = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def __aenter__(self):
        await super().__aenter__()
        for dSource in self._dataSources:
            await dSource.__aenter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        for dSource in self._dataSources:
            await dSource.__aexit__(*args)

    def register_datasource(self, dataSource: DataSource):
        new_component_trait_name = f"dataSource{len(self._dataSources)}"
        self.add_traits(**{new_component_trait_name: Instance(DataSource)})
        self.setAttribute(new_component_trait_name, dataSource)

        def setCurrentData(dataset):
            dataset.dataSource = dataSource
            self.set_trait('currentData', dataset)

        dataSource.addDataSetReadyCallback(setCurrentData)

        self._dataSources.append(dataSource)

    @action("Stop acquisition")
    def stop_acq(self):
        async def _impl():
            for dSource in self._dataSources:
                await dSource.stop()

        self._loop.create_task(_impl())

    @action("Start acquisition")
    def start_acq(self):
        async def _impl():
            for dSource in self._dataSources:
                await dSource.start()

        self._loop.create_task(_impl())

    async def readDataSet(self):
        return self._dataSources[0].currentData

