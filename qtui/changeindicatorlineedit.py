# -*- coding: utf-8 -*-
"""
Created on Mon Jul 11 13:18:40 2016

@author: Arno Rehn
"""

from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtGui import QPalette


def ChangeIndicatorLineEdit(*args, actual_value_getter, **kwargs):
    lineEdit = QLineEdit(*args, **kwargs)

    lineEdit.unchanged_palette = lineEdit.palette()

    lineEdit.changed_palette = lineEdit.palette()
    highlightColor = lineEdit.changed_palette.color(QPalette.Highlight)
    highlightColor.setHsl(0xFF - highlightColor.hslHue(),
                          highlightColor.hslSaturation(),
                          highlightColor.lightness())

    lineEdit.changed_palette.setColor(QPalette.Base, highlightColor)

    def check_changed():
        actualValue = actual_value_getter()
        if lineEdit.text() != actualValue:
            lineEdit.setPalette(lineEdit.changed_palette)
        else:
            lineEdit.setPalette(lineEdit.unchanged_palette)

    lineEdit.check_changed = check_changed
    lineEdit.textChanged.connect(lineEdit.check_changed)

    return lineEdit
