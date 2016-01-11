# -*- coding: utf-8 -*-
"""
Created on Tue Oct 13 13:08:57 2015

@author: Arno Rehn
"""

import asyncio
import enum
import numpy as np
import inspect


def published_action(func):
    func._published_action = True
    return func


class TimeoutException(Exception):
    pass


class ComponentBase:
    def __init__(self, objectName=None, loop=None):
        self.objectName = objectName
        if self.objectName is None:
            self.objectName = ""

        self._loop = loop
        if self._loop is None:
            self._loop = asyncio.get_event_loop()

        self.__actions = []
        self.__attributes = []
        self.__components = []

        for name, memb in inspect.getmembers(self):
            if callable(memb) and getattr(memb, "_published_action", False):
                self.__actions += [name]

    @property
    def actions(self):
        return self.__actions

    @property
    def attributes(self):
        return self.__attributes

    @property
    def components(self):
        return self.__components

    def getAttribute(self, name):
        return getattr(self, name)

    def setAttribute(self, name, val):
        setattr(self, name, val)

    def _publishActions(self, *methods):
        self.__actions += methods

    def _publishAttributes(self, *attributes):
        self.__attributes += attributes

    def _publishComponents(self, *components):
        self.__components += components

    def saveConfiguration(self):
        pass

    def loadConfiguration(self):
        pass


class DataSource(ComponentBase):

    @published_action
    def start(self):
        pass

    @published_action
    def stop(self):
        pass

    @published_action
    def restart(self):
        self.stop()
        self.start()

    @published_action
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
    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)
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
    def __init__(self, source=None, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)
        self.source = source

    @published_action
    def start(self):
        return self._source.start()

    @published_action
    def stop(self):
        return self._source.stop()

    @published_action
    async def readDataSet(self):
        return self.process(await self._source.readDataSet())


class DataSet:
    def __init__(self, data=None, axes=None):
        super().__init__()
        if data is None:
            data = np.array(0.0)
        if axes is None:
            axes = []
        self.data = data
        self.axes = axes

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
