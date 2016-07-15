# -*- coding: utf-8 -*-
"""
Created on Wed Jun 22 14:53:15 2016

@author: Arno Rehn
"""

import pint
from pint import UnitRegistry, set_application_registry

ureg = UnitRegistry()
Q_ = ureg.Quantity
set_application_registry(ureg)

if pint.__version__ == '0.7.2':

    UnitsContainer = pint.unit.UnitsContainer

    def __unbugged_format__(self, spec):
        spec = spec or self.default_format
        # special cases
        if 'Lx' in spec: # the LaTeX siunitx code
          opts = ''
          ustr = pint.unit.siunitx_format_unit(self)
          ret = r'\si[%s]{%s}'%( opts, ustr )
          return ret


        if '~' in spec:
            if not self._units:
                return ''
            units = UnitsContainer(dict((self._REGISTRY._get_symbol(key),
                                         value)
                                   for key, value in self._units.items()))
            spec = spec.replace('~', '')
        else:
            units = self._units

        return '%s' % (format(units, spec))

    pint.unit._Unit.__format__ = __unbugged_format__
