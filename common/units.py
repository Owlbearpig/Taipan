# -*- coding: utf-8 -*-
"""
Created on Wed Jun 22 14:53:15 2016

@author: Arno Rehn
"""

from pint import UnitRegistry, set_application_registry

ureg = UnitRegistry()
Q_ = ureg.Quantity
set_application_registry(ureg)
