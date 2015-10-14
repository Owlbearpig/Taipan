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

    async def moveTo(self, val):
        pass

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, val):
        self._step = val

    async def scan(self):
        pass

class PostProcessor(DataSource, DataSink):
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
