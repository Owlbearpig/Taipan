# -*- coding: utf-8 -*-
"""
Created on Tue Jun 21 09:30:01 2016

@author: Arno Rehn
"""

import wrapt
from functools import partial
from traitlets import parse_notifier_name, All


class UnitConversionManipulatorProxy(wrapt.ObjectProxy):

    def __init__(self, wrapped):
        super().__init__(wrapped)

    @classmethod
    def toManipulatorUnits(cls, value):
        pass

    @classmethod
    def fromManipulatorUnits(cls, value):
        pass

    @property
    def unit(self):
        pass

    @property
    def value(self):
        return self.fromManipulatorUnits(self.__wrapped__.value)

    @property
    def velocity(self):
        return self.fromManipulatorUnits(self.__wrapped__.velocity)

    @velocity.setter
    def velocity(self, val):
        self.__wrapped__.velocity = self.toManipulatorUnits(val)

    @classmethod
    def _handler_wrapper(cls, change, handler):
        change['new'] = cls.fromManipulatorUnits(change['new'])
        change['old'] = cls.fromManipulatorUnits(change['old'])
        handler(change)

    def observe(self, handler, names=All, type='change'):
        names = parse_notifier_name(names)
        for n in names:
            if n in ['velocity', 'value']:
                handler = partial(self._handler_wrapper, handler=handler)

            self._add_notifiers(handler, n, type)

    async def moveTo(self, val: float, velocity=None):
        return await self.__wrapped__.moveTo(self.toManipulatorUnits(val),
                                             self.toManipulatorUnits(velocity))

    async def configureTrigger(self, step, start=None, stop=None):
        step, start, stop = await self.__wrapped__.configureTrigger(
            self.toManipulatorUnits(step), self.toManipulatorUnits(start),
            self.toManipulatorUnits(stop)
        )
        return (self.fromManipulatorUnits(step),
                self.fromManipulatorUnits(start),
                self.fromManipulatorUnits(stop))

    @property
    def triggerStart(self):
        return self.fromManipulatorUnits(self.__wrapped__.triggerStart)

    @property
    def triggerStop(self):
        return self.fromManipulatorUnits(self.__wrapped__.triggerStop)

    @property
    def triggerStep(self):
        return self.fromManipulatorUnits(self.__wrapped__.triggerStep)
