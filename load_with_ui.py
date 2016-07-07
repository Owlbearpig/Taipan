#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jun 19 16:17:42 2016

@author: pumphaus
"""

import matplotlib
# Force usage of the Qt5 backend
matplotlib.use("Qt5Agg")

from qtui.autoui import generate_ui
import quamash
from PyQt5 import QtWidgets
import asyncio
import sys
from os.path import basename, splitext
import logging


class QTextBrowserLoggingHandler(logging.Handler):
    terminator = '\n'

    def __init__(self, textBrowser):
        logging.Handler.__init__(self)
        self.textBrowser = textBrowser

    def emit(self, record):
        try:
            msg = self.format(record)
            text = self.textBrowser.toPlainText()
            text += msg + self.terminator
            self.textBrowser.setPlainText(text)
            self.textBrowser.verticalScrollBar().setValue(
                self.textBrowser.verticalScrollBar().maximum()
            )
        except Exception:
            self.handleError(record)

async def run(app, rootClass, loop):
    async with rootClass() as root:
        w, msgBrowser = generate_ui(root)

        logging.captureWarnings(True)
        handler = QTextBrowserLoggingHandler(msgBrowser)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        w.show()

        aboutToQuit = asyncio.Future(loop=loop)
        app.aboutToQuit.connect(lambda: aboutToQuit.set_result(True))
        await aboutToQuit


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    loop = quamash.QEventLoop(app)
    asyncio.set_event_loop(loop)

    filename = sys.argv[1]
    theglobals = { '__name__': splitext(basename(filename))[0] }
    exec(compile(open(filename, 'rb').read(), filename, 'exec'), theglobals)

    rootClass = theglobals['AppRoot']

    with loop:
        sys.exit(loop.run_until_complete(run(app, rootClass, loop)))
