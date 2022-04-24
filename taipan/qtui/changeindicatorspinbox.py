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

from PyQt5.QtWidgets import QSpinBox, QDoubleSpinBox
from PyQt5.QtGui import QPalette


def ChangeIndicatorSpinBox(*args, actual_value_getter,
                           is_double_spinbox=False, **kwargs):
    if is_double_spinbox:
        spinbox = QDoubleSpinBox(*args, **kwargs)
        spinbox.setDecimals(3)
    else:
        spinbox = QSpinBox(*args, **kwargs)

    spinbox.unchanged_palette = spinbox.palette()

    spinbox.changed_palette = spinbox.palette()
    highlightColor = spinbox.changed_palette.color(QPalette.Highlight)
    highlightColor.setHsl(0xFF - highlightColor.hslHue(),
                          highlightColor.hslSaturation(),
                          highlightColor.lightness())

    spinbox.changed_palette.setColor(QPalette.Base, highlightColor)

    def check_changed():
        actualValue = actual_value_getter()
        if spinbox.value() != actualValue:
            spinbox.setPalette(spinbox.changed_palette)
        else:
            spinbox.setPalette(spinbox.unchanged_palette)

    spinbox.check_changed = check_changed
    spinbox.valueChanged.connect(spinbox.check_changed)

    return spinbox
