# -*- coding: utf-8 -*-
"""
Created on Mon Jun 20 09:10:41 2016

@author: Arno Rehn
"""

import traitlets
import common


class DataSet(traitlets.TraitType):
    """A trait for a DataSet."""

    default_value = common.DataSet()
    info_text = 'a DataSet instance'

    def validate(self, obj, value):
        if isinstance(value, common.DataSet):
            value.checkConsistency()
            return value
        self.error(obj, value)
