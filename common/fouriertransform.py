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

from .common import PostProcessor
import numpy as np
from copy import deepcopy
from traitlets import Enum, Float
import enum
from scipy.signal import windows

class FourierTransform(PostProcessor):

    @enum.unique
    class WindowTypes(enum.Enum):
        Rectangular = 0
        Hann = 1
        Blackman = 2
        Flattop = 3
        Tukey = 4

    windowType = Enum(WindowTypes, WindowTypes.Hann,
                      help="The type of window to apply before doing the "
                           "Fourier transform").tag(name="Window type")

    alpha = Float(0.5, min=0, max=1, help="The alpha parameter of the Tukey"
                                          "window").tag(
                       name="Alpha (Tukey window)")

    def process(self, data):
        data = deepcopy(data)

        winData = data.data
        if self.windowType == FourierTransform.WindowTypes.Hann:
            winData *= windows.hann(len(winData), sym=False)
        elif self.windowType == FourierTransform.WindowTypes.Blackman:
            winData *= windows.blackman(len(winData), sym=False)
        elif self.windowType == FourierTransform.WindowTypes.Flattop:
            winData *= windows.flattop(len(winData), sym=False)
        elif self.windowType == FourierTransform.WindowTypes.Tukey:
            winData *= windows.tukey(len(winData), sym=False, alpha=self.alpha)

        data.data = np.fft.rfft(winData, axis=0, norm='ortho')
        data.axes[0] = np.fft.rfftfreq(len(data.axes[0]),
                                       np.mean(np.diff(data.axes[0])))
        return data
