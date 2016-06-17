# -*- coding: utf-8 -*-
"""
Created on Fri Jun 17 12:51:41 2016

@author: Arno Rehn
"""

from PyQt5 import QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                NavigationToolbar2QT)
from matplotlib.figure import Figure


class MPLCanvas(QtWidgets.QGroupBox):
    """Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        dpi = QtWidgets.qApp.primaryScreen().logicalDotsPerInch() * 0.8
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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fig.tight_layout()

    def drawDataSet(self, dataset):
        self.axes.plot(dataset.axes[0], dataset.data)
        self.canvas.draw()
