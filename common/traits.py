# -*- coding: utf-8 -*-
"""
Created on Mon Jun 20 09:10:41 2016

@author: Arno Rehn
"""

from traitlets import TraitError, class_of, Undefined, TraitType
from .dataset import DataSet as DataSetClass
from .units import ureg, Q_


class DataSet(TraitType):
    """A trait for a DataSet."""

    default_value = DataSetClass()
    info_text = 'a DataSet instance'

    def validate(self, obj, value):
        if isinstance(value, DataSetClass):
            value.checkConsistency()
            return value
        self.error(obj, value)


class Quantity(TraitType):
    """A trait for a Quantity."""

    default_value = Q_(0)
    info_text = 'a quantity'

    def __init__(self, default_value=Undefined,
                 allow_none=None, **kwargs):
        self.dimensionality = kwargs.pop('dimensionality', None)
        self.min = kwargs.pop('min', None)
        self.max = kwargs.pop('max', None)
        super().__init__(default_value=default_value, allow_none=allow_none,
                         **kwargs)

    def validate(self, obj, value):
        if not isinstance(value, ureg.Quantity):
            self.error(obj, value)

        if (self.dimensionality is not None and
            self.dimensionality != value.dimensionality):
            raise TraitError("The dimensionality of the '%s' trait of %s instance should "
                             "be %s, but a value with dimensionality %s was "
                             "specified" % (self.name, class_of(obj),
                                            self.dimensionality, value.dimensionality))

        if ((self.max is not None and (value > self.max)) or
            (self.min is not None and (value < self.min))):
            raise TraitError("The value of the '%s' trait of %s instance should "
                             "be between %s and %s, but a value of %s was "
                             "specified" % (self.name, class_of(obj),
                                            self.min, self.max, value))
        return value
