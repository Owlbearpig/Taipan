# -*- coding: utf-8 -*-
"""
Created on Tue Oct 13 13:08:57 2015

@author: Arno Rehn
"""

class ComponentBase:
    def saveConfiguration(self):
        pass

    def loadConfiguration(self):
        pass

class DataSource(ComponentBase):
    def start(self):
        pass

    def stop(self):
        pass

    def restart(self):
        self.stop()
        self.start()

    async def readDataSet(self):
        raise NotImplementedError("readDataSet() needs to implemented for DataSources!")

class DAQDevice(DataSource):
    @property
    def unit(self):
        return None

    @property
    def numChannels(self):
        return None

class DataSink(ComponentBase):
    def process(self, data):
        raise NotImplementedError("process() needs to implemented for DataSinks!")

class Manipulator(ComponentBase):
    def __init__(self):
        super().__init__()
        self._minimumValue = 0
        self._maximumValue = 0
        self._step = 0

    @property
    def unit(self):
        return None

    @property
    def minimumValue(self):
        return self._minimumValue

    @minimumValue.setter
    def minimumValue(self, val):
        self._minimumValue = val

    @property
    def maximumValue(self):
        return self._maximumValue

    @maximumValue.setter
    def maximumValue(self, val):
        self._maximumValue = val

    @property
    def value(self):
        return None

    async def beginScan(self, minimumValue):
        """ Moves the manipulator to the starting value of a following continuous scan.

        Typically, this will only need to be re-implemented by manipulators emitting trigger signals: If
        `minimumValue` coincides with a trigger position, the initial trigger pulse might not be emitted at all
        if movement started at exactly `minimumValue`.
        Hence, this method should move the manipulator slightly in front of `minimumValue` so that the first
        trigger actually corresponds to `minimumValue`.

        The default implementation simply awaits ``moveTo(minimumValue)``.

        Parameters
        ----------
        minimumValue (numeric) : The initial position.
        """
        await self.moveTo(minimumValue)

    async def moveTo(self, val):
        pass

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, val):
        self._step = val

class PostProcessor(DataSource, DataSink):
    def __init__(self):
        super().__init__()
        self._source = None

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, source):
        self._source = source

    def start(self):
        return self._source.start()

    def stop(self):
        return self._source.stop()

    async def readDataSet(self):
        return self.process(await self._source.readDataSet())

class DataSet:
    def __init__(self, data = None, axes = None):
        super().__init__()
        self._data = data
        self._axes = axes

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, val):
        self._data = val

    @property
    def axes(self):
        return self._axes

    @axes.setter
    def axes(self, val):
        self._axes = val

    def __repr__(self):
        return 'DataSet(%s, %s)' % (repr(self.data), repr(self.axes))

    def __str__(self):
        return 'DataSet with:\n    %s\n  and axes:\n    %s' % \
        (repr(self.data).replace('\n', '\n    '), \
         repr(self.axes).replace('\n', '\n    '))
