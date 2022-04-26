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

from PyQt5 import QtWidgets, QtGui
import numpy as np
import pyqtgraph as pg
import enum
from scipy.signal import windows
from taipan.common import ureg
import time


def _style_pg():
    _defPal = QtGui.QPalette()

    pg.setConfigOption('antialias', True)
#    pg.setConfigOption('useOpenGL', True)
    pg.setConfigOption('foreground', _defPal.color(QtGui.QPalette.Foreground))


class PyQtGraphPlotter(QtWidgets.QGroupBox):

    @enum.unique
    class WindowTypes(enum.Enum):
        Rectangular = 0
        Hann = 1
        Flattop = 2
        Tukey_5Percent = 3

    windowFunctionMap = {
        WindowTypes.Rectangular:    lambda M: windows.boxcar(M, sym=False),
        WindowTypes.Hann:           lambda M: windows.hann(M, sym=False),
        WindowTypes.Flattop:        lambda M: windows.flattop(M, sym=False),
        WindowTypes.Tukey_5Percent: lambda M: windows.tukey(M, sym=False,
                                                            alpha=0.05),
    }

    dataIsPower = False
    prevDataSet = None
    curDataSet = None

    axes_units = [ureg.dimensionless]
    data_unit = ureg.dimensionless

    def __init__(self, parent=None):
        _style_pg()

        super().__init__(parent)

        pal = self.palette()
        highlightPen = pg.mkPen(pal.color(QtGui.QPalette.Highlight)
                                .darker(120))
        darkerHighlightPen = pg.mkPen(highlightPen.color().darker(120))
        alphaColor = darkerHighlightPen.color()
        alphaColor.setAlphaF(0.25)
        darkerHighlightPen.setColor(alphaColor)

        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.addWidget(QtWidgets.QLabel("Fourier transform window:"))
        self.windowComboBox = QtWidgets.QComboBox(self.toolbar)
        for e in self.WindowTypes:
            self.windowComboBox.addItem(e.name, e)
        self.toolbar.addWidget(self.windowComboBox)
        self.windowComboBox.currentIndexChanged.connect(self._updateFTWindow)

        self.pglwidget = pg.GraphicsLayoutWidget(self)
        self.pglwidget.setBackground(None)

        vbox = QtWidgets.QVBoxLayout(self)
        vbox.addWidget(self.toolbar)
        vbox.addWidget(self.pglwidget)

        self.plot = self.pglwidget.addPlot(row=0, col=0)
        self.ft_plot = self.pglwidget.addPlot(row=1, col=0)

        self.plot.setLabels(title="Data")
        self.ft_plot.setLabels(title="Magnitude spectrum")

        self.plot.showGrid(x=True, y=True)
        self.ft_plot.showGrid(x=True, y=True)

        self._make_plot_background(self.plot)
        self._make_plot_background(self.ft_plot)

        self._lines = []
        self._lines.append(self.plot.plot())
        self._lines.append(self.plot.plot())
        self._lines[0].setPen(darkerHighlightPen)
        self._lines[1].setPen(highlightPen)

        self._ft_lines = []
        self._ft_lines.append(self.ft_plot.plot())
        self._ft_lines.append(self.ft_plot.plot())
        self._ft_lines[0].setPen(darkerHighlightPen)
        self._ft_lines[1].setPen(highlightPen)

        self._lastPlotTime = time.perf_counter()

    def _make_plot_background(self, plot, brush=None):
        if brush is None:
            brush = pg.mkBrush(self.palette().color(QtGui.QPalette.Base))

        vb_bg = QtWidgets.QGraphicsRectItem(plot)
        vb_bg.setRect(plot.vb.rect())
        vb_bg.setBrush(brush)
        vb_bg.setFlag(QtWidgets.QGraphicsItem.ItemStacksBehindParent)
        vb_bg.setZValue(-1e9)
        plot.vb.sigResized.connect(lambda x: vb_bg.setRect(x.geometry()))

    def setLabels(self, axesLabels, dataLabel):
        self.axesLabels = axesLabels
        self.dataLabel = dataLabel

        self.updateLabels()

    def updateLabels(self):
        self.plot.setLabels(bottom='{} [{:C~}]'.format(self.axesLabels[0],
                                                       self.axes_units[0]),
                            left='{} [{:C~}]'.format(self.dataLabel,
                                                     self.data_unit))

        ftUnits = self.data_unit
        if not self.dataIsPower:
            ftUnits = ftUnits ** 2

        self.ft_plot.setLabels(bottom='1 / {} [{:C~}]'.format(
                                 self.axesLabels[0],
                                 (1 / self.axes_units[0]).units),
                               left='Power [dB-({:C~})]'.format(ftUnits))

    def get_ft_data(self, data):
        delta = np.mean(np.diff(data.axes[0]))
        winFn = self.windowFunctionMap[self.windowComboBox.currentData()]
        refUnit = 1 * self.data_unit
        Y = np.fft.rfft(data.data / refUnit * winFn(len(data.data)), axis=0)
        freqs = np.fft.rfftfreq(len(data.axes[0]), delta)
        dBdata = 10 * np.log10(np.abs(Y))
        if not self.dataIsPower:
            dBdata *= 2
        return (freqs, dBdata)

    def _updateFTWindow(self):
        if self.prevDataSet:
            F, dBdata = self.get_ft_data(self.prevDataSet)
            self._ft_lines[0].setData(x=F, y=dBdata)

        if self.curDataSet:
            F, dBdata = self.get_ft_data(self.curDataSet)
            self._ft_lines[1].setData(x=F, y=dBdata)

    def drawDataSet(self, newDataSet, *args):
        plotTime = time.perf_counter()

        # artificially limit the replot rate to 20 Hz
        if (plotTime - self._lastPlotTime < 0.05):
            return

        self._lastPlotTime = plotTime

        self.prevDataSet = self.curDataSet
        self.curDataSet = newDataSet

        if (self.curDataSet.data.units != self.data_unit or
                self.curDataSet.axes[0].units != self.axes_units[0]):
            self.data_unit = self.curDataSet.data.units
            self.axes_units[0] = self.curDataSet.axes[0].units
            self.updateLabels()

        if self.prevDataSet:
            self._lines[0].setData(x=self._lines[1].xData,
                                   y=self._lines[1].yData)
            self._ft_lines[0].setData(x=self._ft_lines[1].xData,
                                      y=self._ft_lines[1].yData)
        if self.curDataSet:
            self._lines[1].setData(x=self.curDataSet.axes[0],
                                   y=self.curDataSet.data)
            F, dBdata = self.get_ft_data(self.curDataSet)
            self._ft_lines[1].setData(x=F, y=dBdata)
