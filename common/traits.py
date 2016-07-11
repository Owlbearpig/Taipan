# -*- coding: utf-8 -*-
"""
Created on Mon Jun 20 09:10:41 2016

@author: Arno Rehn
"""

from traitlets import TraitError, class_of, Undefined, TraitType
from .dataset import DataSet as DataSetClass
from .units import ureg, Q_
import pathlib


class DataSet(TraitType):
    """A trait for a DataSet."""

    default_value = DataSetClass()
    info_text = 'a DataSet instance'

    def validate(self, obj, value):
        if isinstance(value, DataSetClass):
            value.checkConsistency()
            return value
        self.error(obj, value)


class Path(TraitType):
    """A trait for a path."""

    default_value = pathlib.Path()
    info_text = 'a path'

    def __init__(self, default_value=Undefined,
                 allow_none=None, **kwargs):
        self.is_file = kwargs.pop('is_file', True)
        self.is_dir = kwargs.pop('is_dir', True)
        self.must_exist = kwargs.pop('must_exist', True)
        super().__init__(default_value=default_value, allow_none=allow_none,
                         **kwargs)

    def validate(self, obj, value):
        if not isinstance(value, pathlib.Path):
            raise TraitError("'%s' is not a Path object!" % repr(value))

        if self.must_exist:
            if not value.exists():
                raise TraitError("The path '%s' does not exist" % value)
            if self.is_file and not self.is_dir and not value.is_file():
                raise TraitError("The path '%s' is not a file" % value)
            if not self.is_file and self.is_dir and not value.is_dir():
                raise TraitError("The path '%s' is not a directory" % value)
        return value


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

        if ((self.max is not None and (value.to(self.max.units) > self.max)) or
            (self.min is not None and (value.to(self.min.units) < self.min))):
            raise TraitError("The value of the '%s' trait of %s instance should "
                             "be between %s and %s, but a value of %s was "
                             "specified" % (self.name, class_of(obj),
                                            self.min, self.max, value))
        return value
