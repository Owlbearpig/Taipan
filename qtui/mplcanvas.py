# -*- coding: utf-8 -*-
"""
Created on Fri Jun 17 12:51:41 2016

@author: Arno Rehn
"""

from PyQt5 import QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                NavigationToolbar2QT)
from matplotlib.figure import Figure
import matplotlib
import numpy as np
from scipy.signal import windows
from warnings import warn
import enum


def style_mpl():
    _defPal = QtGui.QPalette()
    _defFont = QtGui.QFont()

    highlightColor = _defPal.color(QtGui.QPalette.Highlight).darker(120)
    darkerHighlightColor = highlightColor.darker(120)
    cycler = matplotlib.cycler('color', [darkerHighlightColor.name(),
                                         highlightColor.name()])

    matplotlib.rc("patch", linewidth=0.5, antialiased=True)
    matplotlib.rc("font", size=10, family=_defFont.family())
    matplotlib.rc("legend", fontsize=10, fancybox=True)
    matplotlib.rc("axes", grid=True, linewidth=1, titlesize='large',
                  axisbelow=True,
                  edgecolor=_defPal.color(QtGui.QPalette.Mid).name(),
                  prop_cycle=cycler)

    matplotlib.rc("grid", linestyle='-',
                  color=_defPal.color(QtGui.QPalette.AlternateBase).name())


class MPLCanvas(QtWidgets.QGroupBox):
    """Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.)."""

    @enum.unique
    class WindowTypes(enum.Enum):
        Rectangular = 0
        Hann = 1
        Flattop = 2

    windowFunctionMap = {
        WindowTypes.Rectangular: lambda M: windows.boxcar(M, sym=False),
        WindowTypes.Hann:        lambda M: windows.hann(M, sym=False),
        WindowTypes.Flattop:     lambda M: windows.flattop(M, sym=False),
    }

    def __init__(self, parent=None):
        style_mpl()

        super().__init__(parent)

        dpi = QtWidgets.qApp.primaryScreen().logicalDotsPerInch()
        self.fig = Figure(dpi=dpi)
        self.fig.patch.set_alpha(0)

        self.axes = self.fig.add_subplot(2, 1, 1)
        self.ft_axes = self.fig.add_subplot(2, 1, 2)

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)

        self.mpl_toolbar.addSeparator()
        self.mpl_toolbar.addWidget(QtWidgets.QLabel("Fourier transform "
                                                    "window: "))

        self.windowComboBox = QtWidgets.QComboBox(self.mpl_toolbar)
        for e in MPLCanvas.WindowTypes:
            self.windowComboBox.addItem(e.name, e)
        self.mpl_toolbar.addWidget(self.windowComboBox)
        self.windowComboBox.currentIndexChanged.connect(self._replot)

        vbox = QtWidgets.QVBoxLayout(self)
        vbox.addWidget(self.mpl_toolbar)
        vbox.addWidget(self.canvas)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setStretch(0, 1)
        vbox.setStretch(1, 1)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                  QtWidgets.QSizePolicy.Expanding)
        self.updateGeometry()

        self.fig.tight_layout()

        self.dataSet = None
        self.prevDataSet = None
        self._axesLabels = None
        self._dataLabel = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fig.tight_layout()

    def _drawDataSet(self, data, **kwargs):
        if data is None:
            self.axes.plot([], [], **kwargs)
            self.ft_axes.plot([], [], **kwargs)
            return

        self.axes.plot(data.axes[0], data.data, **kwargs)

        delta = np.mean(np.diff(data.axes[0]))
        print(delta)
        winFn = self.windowFunctionMap[self.windowComboBox.currentData()]
        Y = np.fft.rfft(data.data * winFn(len(data.data)), axis=0)
        Y /= len(Y)
        freqs = np.fft.rfftfreq(len(data.axes[0]), delta)
        self.ft_axes.plot(freqs, 20 * np.log10(np.abs(Y)), **kwargs)

    def _replot(self):
        self.axes.hold(False)
        self.ft_axes.hold(False)
        self._drawDataSet(self.prevDataSet, alpha=.25)

        self.axes.hold(True)
        self.ft_axes.hold(True)
        self._drawDataSet(self.dataSet)

        self.axes.legend(['Previous', 'Current'])
        self.ft_axes.legend(['Previous', 'Current'])

        if self._axesLabels:
            self.axes.set_xlabel('{} [{:C~}]'.format(
                                 self._axesLabels[0], self.dataSet.axes)
            self.ft_axes.set_xlabel('1 / {} [1 / {:C~}]' .format(
                                    self._axesLabels[0],
                                    self.dataSet.axes[0].units))

        if self._dataLabel:
            self.axes.set_ylabel(self._dataLabel)
            self.ft_axes.set_ylabel('(FT Amplitude)² (dB)')

        self.axes.set_title('Data')
        self.ft_axes.set_title('Fourier transformed data')

        self.axes.autoscale()
        self.axes.autoscale_view()
        self.ft_axes.autoscale()
        self.ft_axes.autoscale_view()

        self.fig.tight_layout()

        self.canvas.draw()

    def drawDataSet(self, newDataSet, axes_labels, data_label):
        self.prevDataSet = self.dataSet
        self.dataSet = newDataSet

        self._axesLabels = axes_labels
        self._dataLabel = data_label

        self._replot()
