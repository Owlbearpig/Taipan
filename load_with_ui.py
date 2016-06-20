#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun 19 16:17:42 2016

@author: pumphaus
"""

from qtui.autoui import generate_ui
import quamash
from PyQt5 import QtWidgets
import asyncio
import sys
from os.path import basename, splitext

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    loop = quamash.QEventLoop(app)
    asyncio.set_event_loop(loop)

    filename = sys.argv[1]
    theglobals = { '__name__': splitext(basename(filename))[0] }
    exec(compile(open(filename, 'rb').read(), filename, 'exec'), theglobals)

    root = theglobals['AppRoot']()
    w = generate_ui(root)
    w.show()

    with loop:
        sys.exit(loop.run_forever())
