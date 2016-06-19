#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun 19 16:17:42 2016

@author: pumphaus
"""

from test import AppRoot
from qtui.autoui import generate_ui
import quamash
from PyQt5 import QtWidgets
import asyncio
import sys

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    loop = quamash.QEventLoop(app)
    asyncio.set_event_loop(loop)

    root = AppRoot()

    ui = generate_ui(root)
    ui.show()

    root.positioningVelocity = 20
    root.scanVelocity = 5
    root.maximumValue = 10
    root.step = 0.5

    with loop:
        sys.exit(loop.run_forever())
