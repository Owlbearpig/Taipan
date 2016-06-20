# -*- coding: utf-8 -*-
"""
Created on Mon Jun 20 11:18:59 2016

@author: Arno Rehn
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
