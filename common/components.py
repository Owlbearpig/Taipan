# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2015 - 2016 Arno Rehn <arno@arnorehn.de>

Taipan is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Taipan is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Taipan.  If not, see <http://www.gnu.org/licenses/>.
"""

import asyncio
import enum
import numpy as np
import traitlets
from configparser import ConfigParser
from traitlets import Instance
from copy import deepcopy
from .units import ureg, Q_
from .traits import Quantity


def action(name=None, help=None, **kwargs):
    if name is None:
        name = ''
    if help is None:
        help = ''

    kwargs['name'] = name
    kwargs['help'] = help

    def action_impl(method):
        method._isAction = True
        method.metadata = kwargs
        method.help = help
        return method

    return action_impl


def _dumb_list_of_actions(inst):
    for name in dir(inst):
        try:
            attr = getattr(inst, name, None)
            if not attr._isAction:
                continue

            yield name, attr
        except AttributeError:
            pass
        except traitlets.TraitError:
            pass


def is_component_trait(x):
    return (isinstance(x, Instance) and issubclass(x.klass, ComponentBase))


class ComponentBase(traitlets.HasTraits):

    def __init__(self, objectName: str=None, loop: asyncio.BaseEventLoop=None):
        self.objectName = objectName
        if self.objectName is None:
            self.objectName = ""

        self._loop = loop
        if self._loop is None:
            self._loop = asyncio.get_event_loop()

        self.__actions = []
        for name, memb in _dumb_list_of_actions(self):
            self.__actions.append((name, memb))

    async def __aenter__(self):
        for name, trait in self.traits().items():
            if is_component_trait(trait):
                await trait.get(self).__aenter__()
        return self

    async def __aexit__(self, *args):
        for name, trait in self.traits().items():
            if is_component_trait(trait):
                await trait.get(self).__aexit__(*args)

    @property
    def actions(self):
        return self.__actions

    @property
    def attributes(self):
        return self.traits()

    def getAttribute(self, name):
        return getattr(self, name)

    def setAttribute(self, name, val):
        setattr(self, name, val)

    def saveConfiguration(self, config: ConfigParser):
        for c in self.__components:
            c.saveConfiguration(config)

    def loadConfiguration(self, config: ConfigParser):
        for c in self.__components:
            c.loadConfiguration(config)


class DataSource(ComponentBase):

    def __init__(self, objectName: str=None, loop: asyncio.BaseEventLoop=None):
        super().__init__(objectName=objectName, loop=loop)
        self._dataSetReadyCallbacks = []

    async def start(self):
        pass

    async def stop(self):
        pass

    async def restart(self):
        await self.stop()
        await self.start()

    def addDataSetReadyCallback(self, callback):
        self._dataSetReadyCallbacks.append(callback)

    def removeDataSetReadyCallback(self, callback):
        self._dataSetReadyCallbacks.remove(callback)

    def _dataSetReady(self, dataSet):
        for cb in self._dataSetReadyCallbacks:
            cb(dataSet)

    async def readDataSet(self):
        raise NotImplementedError("readDataSet() needs to implemented for "
                                  "DataSources!")


class DAQDevice(DataSource):

    @property
    def numChannels(self):
        return None


class DataSink(ComponentBase):

    def process(self, data):
        raise NotImplementedError("process() needs to implemented for "
                                  "DataSinks!")


class Manipulator(ComponentBase):

    class Status(enum.Enum):
        Undefined = 0
        TargetReached = 1
        Moving = 2
        Error = 3
        Stopped = 4

    velocity = Quantity(Q_(1)).tag(prettyName="Velocity")
    value = Quantity(Q_(0), read_only=True).tag(prettyName="Value")
    targetValue = Quantity(Q_(0)).tag(prettyName="Target value")
    status = traitlets.Enum(Status, default_value=Status.Undefined,
                            read_only=True)

    def __init__(self, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)
        self._trigStart = None
        self._trigStop = None
        self._trigStep = Q_(0)
        self.__original_class = self.__class__

    def setPreferredUnits(self, units, velocityUnits):
        self.__class__ = self.__original_class

        allTraits = self.traits()

        newValueTrait = deepcopy(allTraits['value'])
        newValueTrait.metadata['preferred_units'] = units
        newValueTrait.default_value = 0 * units

        newTargetValueTrait = deepcopy(allTraits['targetValue'])
        newTargetValueTrait.metadata['preferred_units'] = units
        newTargetValueTrait.default_value = 0 * units

        newVelocityTrait = deepcopy(allTraits['velocity'])
        newVelocityTrait.metadata['preferred_units'] = velocityUnits
        newVelocityTrait.default_value = 1 * velocityUnits

        self.add_traits(value=newValueTrait, targetValue=newTargetValueTrait,
                        velocity=newVelocityTrait)

    @traitlets.observe("targetValue")
    def _targetValueObserver(self, change):
        self._loop.create_task(self.moveTo(change['new']))

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

    async def moveTo(self, val: float, velocity=None):
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

    @action("Stop")
    def stop(self):
        pass


class PostProcessor(DataSource, DataSink):

    def __init__(self, source=None, objectName=None, loop=None):
        super().__init__(objectName=objectName, loop=loop)
        self.source = source

    async def start(self):
        return await self.source.start()

    async def stop(self):
        return await self.source.stop()

    async def readDataSet(self):
        return self.process(await self.source.readDataSet())
