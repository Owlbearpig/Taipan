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

    dataIsPower = False
    dataSet = None
    prevDataSet = None
    _prevAxesLabels = None
    _axesLabels = None
    _prevDataLabel = None
    _dataLabel = None

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

        self._lines = self.axes.plot([], [], [], [], animated=True)
        self._lines[0].set_alpha(0.25)
        self._ftlines = self.ft_axes.plot([], [], [], [], animated=True)
        self._ftlines[0].set_alpha(0.25)
        self.axes.legend(['Previous', 'Current'])
        self.ft_axes.legend(['Previous', 'Current'])
        self.axes.set_title('Data')
        self.ft_axes.set_title('Fourier transformed data')
        self._redraw_background()

    def _redraw_background(self):
        self.fig.tight_layout()
        self.canvas.draw()
        self.backgrounds = [self.fig.canvas.copy_from_bbox(ax.bbox) for ax in
                            (self.axes, self.ft_axes)]

    def showEvent(self, e):
        super().showEvent(e)
        self._redraw_background()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._redraw_background()

    def get_ft_data(self, data):
        delta = np.mean(np.diff(data.axes[0]))
        winFn = self.windowFunctionMap[self.windowComboBox.currentData()]
        refUnit = 1 * data.data.units
        Y = np.fft.rfft(data.data / refUnit * winFn(len(data.data)), axis=0)
        freqs = np.fft.rfftfreq(len(data.axes[0]), delta)
        dBdata = 10 * np.log10(np.abs(Y))
        if not self.dataIsPower:
            dBdata *= 2
        return (freqs, dBdata)

    def _dataSetToLines(self, data, line, ftline):
        if data is None:
            line.set_data([], [])
            ftline.set_data([], [])
            return

        line.set_data(data.axes[0], data.data)
        freqs, dBdata = self.get_ft_data(data)
        ftline.set_data(freqs, dBdata)

    def _replot(self, redraw_axes=False, redraw_axes_labels=False,
                redraw_data_label=False):
        self._dataSetToLines(self.prevDataSet, self._lines[0],
                             self._ftlines[0])
        self._dataSetToLines(self.dataSet, self._lines[1], self._ftlines[1])

        if self._axesLabels and redraw_axes_labels:
            self.axes.set_xlabel('{} [{:C~}]'.format(
                                 self._axesLabels[0],
                                 self.dataSet.axes[0].units))
            self.ft_axes.set_xlabel('1 / {} [1 / {:C~}]' .format(
                                    self._axesLabels[0],
                                    self.dataSet.axes[0].units))

        if self._dataLabel and redraw_data_label:
            self.axes.set_ylabel('{} [{:C~}]'.format(
                                 self._dataLabel,
                                 self.dataSet.data.units))

            ftUnits = self.dataSet.data.units
            if not self.dataIsPower:
                ftUnits = ftUnits ** 2

            self.ft_axes.set_ylabel('Power [dB-({:C~})]'.format(ftUnits))

        redraw_axes = redraw_axes or redraw_axes_labels or redraw_data_label

        if redraw_axes:
            self.axes.relim()
            self.axes.autoscale_view()
            self.ft_axes.relim()
            self.ft_axes.autoscale_view()
            self.canvas.draw()
        else:
            for bg in self.backgrounds:
                self.canvas.restore_region(bg)

        self.axes.draw_artist(self._lines[0])
        self.axes.draw_artist(self._lines[1])
        self.ft_axes.draw_artist(self._ftlines[0])
        self.ft_axes.draw_artist(self._ftlines[1])

        if not redraw_axes:
            self.canvas.blit(self.axes.bbox)
            self.canvas.blit(self.ft_axes.bbox)

    def drawDataSet(self, newDataSet, axes_labels, data_label):
        self.prevDataSet = self.dataSet
        self.dataSet = newDataSet

        redraw_axes = (self.prevDataSet is None or
                       not np.array_equal(self.prevDataSet.axes,
                                          self.dataSet.axes))

        redraw_axes_labels = (self._axesLabels != axes_labels or
                              self.prevDataSet and self.dataSet and
                              self.prevDataSet.axes[0].units !=
                                  self.dataSet.axes[0].units)
        redraw_data_label = (self._dataLabel != data_label or
                             self.prevDataSet and self.dataSet and
                             self.prevDataSet.data.units !=
                                 self.dataSet.data.units)

        self._axesLabels = axes_labels
        self._dataLabel = data_label

        self._replot(redraw_axes, redraw_axes_labels, redraw_data_label)
