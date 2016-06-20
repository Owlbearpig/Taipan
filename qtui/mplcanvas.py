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
from warnings import warn


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

    def __init__(self, parent=None):
        style_mpl()

        super().__init__(parent)

        dpi = QtWidgets.qApp.primaryScreen().logicalDotsPerInch()
        self.fig = Figure(dpi=dpi)
        self.fig.patch.set_alpha(0)

        self.axes = self.fig.add_subplot(111)

        # We want the axes cleared every time plot() is called
        self.axes.hold(False)

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)

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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fig.tight_layout()

    def _draw(self, data, logscale, **kwargs):
        if data is None:
            self.axes.plot([], [], alpha=.25)
            return

        dataArray = data.data
        if np.iscomplexobj(dataArray):
            warn("Plot function received complex array."
                 "Plotting magnitude only")
            dataArray = np.abs(dataArray)

        plotfn = self.axes.semilogy if logscale else self.axes.plot
        plotfn(data.axes[0], dataArray, **kwargs)

    def drawDataSet(self, dataset, axes_labels, data_label, logscale=False):
        self.axes.hold(False)
        self._draw(self.dataSet, alpha=.25, logscale=logscale)
        self.axes.hold(True)
        self._draw(dataset, logscale=logscale)

        self.axes.legend(['Previous', 'Current'])

        self.dataSet = dataset

        if axes_labels:
            self.axes.set_xlabel(axes_labels[0])
        self.axes.set_ylabel(data_label)

        self.axes.autoscale()
        self.axes.autoscale_view()
        self.fig.tight_layout()

        self.canvas.draw()
