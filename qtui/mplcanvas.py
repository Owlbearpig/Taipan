# -*- coding: utf-8 -*-
"""
Created on Fri Jun 17 12:51:41 2016

@author: Arno Rehn
"""

from PyQt5 import QtWidgets, QtGui, QtCore
from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                NavigationToolbar2QT)
from matplotlib.figure import Figure


class MPLCanvas(QtWidgets.QWidget):
    """Ultimately, this is a QWidget (as well as a FigureCanvasAgg, etc.)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        dpi = QtWidgets.qApp.primaryScreen().logicalDotsPerInch()
        fig = Figure(dpi=dpi)
        self.axes = fig.add_subplot(111)
        # We want the axes cleared every time plot() is called
        self.axes.hold(False)

        self.canvas = FigureCanvasQTAgg(fig)
        self.mpl_toolbar = NavigationToolbar2QT(self.canvas, self)

        vbox = QtWidgets.QVBoxLayout(self)
        vbox.addWidget(self.canvas)
        vbox.addWidget(self.mpl_toolbar)
        vbox.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        self.updateGeometry()

        self.axes.plot([0, 1, 2], [5, 6, 7])

