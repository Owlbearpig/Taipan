# -*- coding: utf-8 -*-
"""
Created on Wed Jun 22 14:54:44 2016

@author: Arno Rehn
"""

import numpy as np
from .units import Q_

class DataSet:

    def __init__(self, data=None, axes=None):
        super().__init__()
        if data is None:
            data = Q_(np.array(0.0))
        if axes is None:
            axes = []
        self.data = data
        self.axes = axes

    @property
    def isConsistent(self):
        return len(self.axes) == self.data.ndim and \
               all([len(ax) == shape
                    for (ax, shape) in zip(self.axes, self.data.shape)])

    def checkConsistency(self):
        if not self.isConsistent:
            raise Exception("DataSet is inconsistent! "
                            "Number of axes: %d, data dimension: %d, "
                            "axes lengths: %s, data shape: %s" %
                            (len(self.axes), self.data.ndim,
                             [len(ax) for ax in self.axes],
                             self.data.shape))

    def __repr__(self):
        return 'DataSet(%s, %s)' % (repr(self.data), repr(self.axes))

    def __str__(self):
        return 'DataSet with:\n    %s\n  and axes:\n    %s' % \
                (repr(self.data).replace('\n', '\n    '),
                 repr(self.axes).replace('\n', '\n    '))
