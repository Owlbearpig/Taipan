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
import os

from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                NavigationToolbar2QT)
from matplotlib.figure import Figure
import matplotlib
import numpy as np
from scipy.signal import windows
import enum
import time


def style_mpl():
    _defPal = QtGui.QPalette()
    _defFont = QtGui.QFont()
    if "nt" in os.name:
        _defFont.setFamily("Arial")

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
        Tukey_5Percent = 3

    windowFunctionMap = {
        WindowTypes.Rectangular: lambda M: windows.boxcar(M, sym=False),
        WindowTypes.Hann: lambda M: windows.hann(M, sym=False),
        WindowTypes.Flattop: lambda M: windows.flattop(M, sym=False),
        WindowTypes.Tukey_5Percent: lambda M: windows.tukey(M, sym=False,
                                                            alpha=0.05),
    }

    dataIsPower = False
    dataSet = None
    prevDataSet = None
    _prevAxesLabels = None
    _axesLabels = None
    _prevDataLabel = None
    _dataLabel = None

    _lastPlotTime = 0
    _isLiveData = False

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

        self.autoscaleAction = self.mpl_toolbar.addAction("Auto-scale")
        self.autoscaleAction.setCheckable(True)
        self.autoscaleAction.setChecked(True)
        self.autoscaleAction.triggered.connect(self._autoscale)

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
        self._redraw()

        # Use a timer with a timeout of 0 to initiate redrawing of the canvas.
        # This ensures that the eventloop has run once more and prevents
        # artifacts.
        self._redrawTimer = QtCore.QTimer(self)
        self._redrawTimer.setSingleShot(True)
        self._redrawTimer.setInterval(100)
        self._redrawTimer.timeout.connect(self._redraw)

        # will be disconnected in drawDataSet() when live data is detected.
        self._redraw_id = self.canvas.mpl_connect('draw_event',
                                                  self._redraw_artists)

    def _redraw_artists(self, *args):
        if not self._isLiveData:
            self.axes.draw_artist(self._lines[0])
            self.ft_axes.draw_artist(self._ftlines[0])
        self.axes.draw_artist(self._lines[1])
        self.ft_axes.draw_artist(self._ftlines[1])

    def _redraw(self):
        self.fig.tight_layout()
        self.canvas.draw()
        self.backgrounds = [self.fig.canvas.copy_from_bbox(ax.bbox) for ax in
                            (self.axes, self.ft_axes)]
        self._redraw_artists()

    def showEvent(self, e):
        super().showEvent(e)
        self._redrawTimer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._redrawTimer.start()

    def get_ft_data(self, data):
        delta = np.mean(np.diff(data.axes[0].magnitude))
        winFn = self.windowFunctionMap[self.windowComboBox.currentData()]
        Y = np.fft.rfft(data.data.magnitude * winFn(len(data.data)), axis=0)
        freqs = np.fft.rfftfreq(len(data.axes[0]), delta)
        dBdata = 10 * np.log10(np.abs(Y))
        if not self.dataIsPower:
            dBdata *= 2
        return freqs, dBdata

    def _dataSetToLines(self, data, line, ftline):
        if data is None:
            line.set_data([], [])
            ftline.set_data([], [])
            return

        # data.data -= np.mean(data.data)
        line.set_data(data.axes[0].magnitude, data.data.magnitude)
        freqs, dBdata = self.get_ft_data(data)
        ftline.set_data(freqs, dBdata)

    def _autoscale(self, *, redraw=True):
        prev_xlim = self.axes.get_xlim()
        prev_ylim = self.axes.get_ylim()
        prev_ft_xlim = self.ft_axes.get_xlim()
        prev_ft_ylim = self.ft_axes.get_ylim()

        self.axes.relim()
        self.axes.autoscale()
        self.ft_axes.relim()
        self.ft_axes.autoscale()

        need_redraw = (prev_xlim != self.axes.get_xlim() or
                       prev_ylim != self.axes.get_ylim() or
                       prev_ft_xlim != self.ft_axes.get_xlim() or
                       prev_ft_ylim != self.ft_axes.get_ylim())

        if need_redraw and redraw:
            self._redraw()

        return need_redraw

    def _replot(self, redraw_axes=False, redraw_axes_labels=False,
                redraw_data_label=False):
        if not self._isLiveData:
            self._dataSetToLines(self.prevDataSet, self._lines[0],
                                 self._ftlines[0])
        self._dataSetToLines(self.dataSet, self._lines[1], self._ftlines[1])

        if self._axesLabels and redraw_axes_labels:
            self.axes.set_xlabel('{} [{:C~}]'.format(
                self._axesLabels[0],
                self.dataSet.axes[0].units))
            self.ft_axes.set_xlabel('1 / {} [1 / {:C~}]'.format(
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

        axis_limits_changed = False
        if (self.autoscaleAction.isChecked()):
            axis_limits_changed = self._autoscale(redraw=False)

        # check whether a full redraw is necessary or if simply redrawing
        # the data lines is enough
        if (redraw_axes or redraw_axes_labels or
                redraw_data_label or axis_limits_changed):
            self._redraw()
        else:
            for bg in self.backgrounds:
                self.canvas.restore_region(bg)
            self._redraw_artists()
            self.canvas.blit(self.axes.bbox)
            self.canvas.blit(self.ft_axes.bbox)

    def drawDataSet(self, newDataSet, axes_labels, data_label):
        plotTime = time.perf_counter()

        looksLikeLiveData = plotTime - self._lastPlotTime < 1

        if looksLikeLiveData != self._isLiveData:
            if looksLikeLiveData:
                self.canvas.mpl_disconnect(self._redraw_id)
            else:
                self._redraw_id = self.canvas.mpl_connect('draw_event',
                                                          self._redraw_artists)

        self._isLiveData = looksLikeLiveData

        # artificially limit the replot rate to 5 Hz
        if (plotTime - self._lastPlotTime < 0.2):
            return

        self._lastPlotTime = plotTime

        self.prevDataSet = self.dataSet
        self.dataSet = newDataSet

        redraw_axes = (self.prevDataSet is None or
                       len(self.prevDataSet.axes) != len(self.dataSet.axes))
        if not redraw_axes:
            for x, y in zip(self.prevDataSet.axes, self.dataSet.axes):
                if x.units != y.units:
                    redraw_axes = True
                    break

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


class MPLMSCanvas(MPLCanvas):
    _dataSources = []
    _lastPlotTime = {}
    _isLiveDataDict = {}
    prevDataSetDict = {}
    _linesDict = {}
    _ftlinesDict = {}
    colors = ["b", "g", "r", "c", "m", "y", "k", "w"]

    def __init__(self, trait, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.mpl_toolbar.addSeparator()

        self._dataSources = trait.registered_dataSources

        self.mpl_toolbar.addWidget(QtWidgets.QLabel("Show datasource: "))
        self.datasourceComboBox = QtWidgets.QComboBox(self.mpl_toolbar)
        self.datasourceComboBox.addItem("All", 0)
        for i, ds in enumerate(self._dataSources):
            self.datasourceComboBox.addItem(ds.objectName, i+1)
        self.mpl_toolbar.addWidget(self.datasourceComboBox)
        self.datasourceComboBox.currentIndexChanged.connect(self._replot)

        for i, dataSource in enumerate(self._dataSources):
            self._lastPlotTime[dataSource] = 0
            self._isLiveDataDict[dataSource] = False
            self.prevDataSetDict[dataSource] = None
            self._linesDict[dataSource] = []
            self._ftlinesDict[dataSource] = []

            c = self.colors[i]
            self._linesDict[dataSource].extend(
                self.axes.plot([], [], animated=True, c=c, label=dataSource.objectName + " previous"))
            self._linesDict[dataSource].extend(
                self.axes.plot([], [], animated=True, c=c, label=dataSource.objectName))
            self._linesDict[dataSource][0].set_alpha(0.25)

            self._ftlinesDict[dataSource].extend(
                self.ft_axes.plot([], [], animated=True, c=c, label=dataSource.objectName + " previous"))
            self._ftlinesDict[dataSource].extend(
                self.ft_axes.plot([], [], animated=True, c=c, label=dataSource.objectName))
            self._ftlinesDict[dataSource][0].set_alpha(0.25)

        self.axes.legend()
        self.ft_axes.legend()

        self._redraw()

    def drawDataSet(self, newDataSet, axes_labels, data_label):
        dataSource = newDataSet.dataSource_inst

        self._lines = self._linesDict[dataSource]
        self._ftlines = self._ftlinesDict[dataSource]

        plotTime = time.perf_counter()

        looksLikeLiveData = plotTime - self._lastPlotTime[dataSource] < 1

        if looksLikeLiveData != self._isLiveDataDict[dataSource]:
            if looksLikeLiveData:
                self.canvas.mpl_disconnect(self._redraw_id)
            else:
                self._redraw_id = self.canvas.mpl_connect('draw_event',
                                                          self._redraw_artists)

        self._isLiveDataDict[dataSource] = looksLikeLiveData
        self._isLiveData = self._isLiveDataDict[dataSource]

        # artificially limit the replot rate to 5 Hz
        if (plotTime - self._lastPlotTime[dataSource] < 0.2):
            return

        self._lastPlotTime[dataSource] = plotTime

        self.prevDataSet = self.prevDataSetDict[dataSource]

        self.dataSet = newDataSet
        self.prevDataSetDict[dataSource] = self.dataSet

        redraw_axes = (self.prevDataSet is None or
                       len(self.prevDataSet.axes) != len(self.dataSet.axes))
        if not redraw_axes:
            for x, y in zip(self.prevDataSet.axes, self.dataSet.axes):
                if x.units != y.units:
                    redraw_axes = True
                    break

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

    def _redraw_artists(self, *args):
        for dsource in self._dataSources:
            lines, ftlines = self._linesDict[dsource], self._ftlinesDict[dsource]
            isLiveData = self._isLiveDataDict[dsource]
            if not isLiveData:
                self.axes.draw_artist(lines[0])
                self.ft_axes.draw_artist(ftlines[0])
            self.axes.draw_artist(lines[1])
            self.ft_axes.draw_artist(ftlines[1])
