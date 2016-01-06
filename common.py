# -*- coding: utf-8 -*-
"""
Created on Tue Oct 13 13:08:57 2015

@author: Arno Rehn
"""

import asyncio
import enum
import numpy as np


class TimeoutException(Exception):
    pass


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
        raise NotImplementedError("readDataSet() needs to implemented for "
                                  "DataSources!")


class DAQDevice(DataSource):
    @property
    def unit(self):
        return None

    @property
    def numChannels(self):
        return None


class DataSink(ComponentBase):
    def process(self, data):
        raise NotImplementedError("process() needs to implemented for "
                                  "DataSinks!")


class Manipulator(ComponentBase):
    def __init__(self):
        super().__init__()
        self._trigStart = None
        self._trigStop = None
        self._trigStep = 0
        self.__velocity = 0

    @property
    def velocity(self):
        return self.__velocity

    @velocity.setter
    def velocity(self, value):
        self.__velocity = value

    @property
    def unit(self):
        return None

    @property
    def value(self):
        return None

    class Status(enum.Enum):
        Undefined = 0
        TargetReached = 1
        Moving = 2
        Error = 3

    @property
    def status(self):
        return Manipulator.Status.Undefined

    async def waitForTargetReached(self, timeout=30):
        """ Wait for the Manipulator's status to become ``TargetReached``.
        Throws a TimeoutException if the method has been waiting for longer
        than ``timeout`` seconds.

        The default implementation simply polls the ``status`` property every
        100 ms. Subclasses can implement a more efficient waiting method.

        Parameters
        ----------
        timeout (numeric) : The time in seconds after which the method throws a
        TimeoutException.
        """
        waited = 0
        while self.status != self.Status.TargetReached and waited < timeout:
            await asyncio.sleep(0.1)
            waited += 0.1

        if (self.status != self.Status.TargetReached):
            raise asyncio.TimeoutError("Timed out after waiting %s seconds for"
                                       " the manipulator %s to reach the "
                                       "target value." %
                                       (str(timeout), str(self)))


    async def beginScan(self, start, stop, velocity=None):
        """ Moves the manipulator to the starting value of a following
        continuous scan.

        Typically, this will only need to be re-implemented by manipulators
        emitting trigger signals: If `start` coincides with a trigger
        position, the initial trigger pulse might not be emitted at all
        if movement started at exactly `start`.
        Hence, this method should move the manipulator slightly in front of
        `start` so that the first trigger actually corresponds to
        `start`.

        The default implementation simply awaits ``moveTo(start)``.

        Parameters
        ----------
        start (numeric) : The initial value.

        stop (numeric) : The final value. Used to determine the direction of
        movement.
        """
        await self.moveTo(start, velocity)

    async def moveTo(self, val, velocity=None):
        pass

    async def configureTrigger(self, step, start=None, stop=None):
        """ Configure the trigger output.

        Paramters
        ---------
        step (numeric) : The trigger distance.

        start (numeric, optional) : The trigger start value.

        stop (numeric, optional) : The trigger stop value.

        Returns
        -------
        tuple(triggerStep, triggerStart, triggerStop) : The effectively set
        trigger parameters
        """
        self._trigStep = step
        self._trigStart = start
        self._trigStop = stop
        return (self._trigStep, self._trigStart, self._trigStop)

    @property
    def triggerStart(self):
        """ The trigger start value.
        """
        return self._trigStart

    @property
    def triggerStop(self):
        """ The trigger stop value.
        """
        return self._trigStop

    @property
    def triggerStep(self):
        """ The trigger distance.
        """
        return self._trigStep

    def stop(self):
        pass


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
    def __init__(self, data=np.array(0.0), axes=[]):
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

    @property
    def isConsistent(self):
        return len(self._axes) == self._data.ndim and \
               all([len(ax) == shape
                    for (ax, shape) in zip(self._axes, self._data.shape)])

    def checkConsistency(self):
        if not self.isConsistent:
            raise Exception("DataSet is inconsistent! "
                            "Number of axes: %d, data dimension: %d, "
                            "axes lengths: %s, data shape: %s" %
                            (len(self._axes), self._data.ndim,
                             [len(ax) for ax in self._axes],
                             self._data.shape))

    def __repr__(self):
        return 'DataSet(%s, %s)' % (repr(self.data), repr(self.axes))

    def __str__(self):
        return 'DataSet with:\n    %s\n  and axes:\n    %s' % \
                (repr(self.data).replace('\n', '\n    '),
                 repr(self.axes).replace('\n', '\n    '))
