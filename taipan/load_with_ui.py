#!/usr/bin/env python3
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

import matplotlib
# Force usage of the Qt5 backend
matplotlib.use("Qt5Agg")

from qtui.autoui import generate_ui
import qasync
from PyQt5 import QtCore, QtWidgets
import asyncio
import sys
from os.path import basename, splitext
import logging


class QTextBrowserLoggingHandler(QtCore.QObject, logging.Handler):
    terminator = '\n'

    def __init__(self, textBrowser):
        super().__init__()
        self.textBrowser = textBrowser

        self._logMetaMethod = self.metaObject().method(
            self.metaObject().indexOfMethod("logFormattedMessage(QString)"))

    @QtCore.pyqtSlot(str)
    def logFormattedMessage(self, msg):
        text = self.textBrowser.toPlainText()
        lines = text.split(self.terminator)
        lines = lines[-100:]  # restrict to 100 lines of backlog
        lines.append(msg)
        text = self.terminator.join(lines)
        self.textBrowser.setPlainText(text)
        self.textBrowser.verticalScrollBar().setValue(
            self.textBrowser.verticalScrollBar().maximum()
        )

    def emit(self, record):
        msg = self.format(record)
        self._logMetaMethod.invoke(self, QtCore.Qt.QueuedConnection,
                                   QtCore.Q_ARG(str, msg))


async def run(app, rootClass, loop):
    async with rootClass() as root:
        w, msgBrowser = generate_ui(root)
        w.resize(1024, 480)

        logging.captureWarnings(True)
        handler = QTextBrowserLoggingHandler(msgBrowser)
        formatter = logging.Formatter('%(asctime)s:%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        w.show()

        lastWindowClosed = asyncio.Future(loop=loop)
        app.lastWindowClosed.connect(lambda: lastWindowClosed.set_result(True))
        await lastWindowClosed

        logging.getLogger().removeHandler(handler)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    filename = sys.argv[1]
    theglobals = { '__name__': splitext(basename(filename))[0] }
    exec(compile(open(filename, 'rb').read(), filename, 'exec'), theglobals)

    rootClass = theglobals['AppRoot']

    with loop:
        sys.exit(loop.run_until_complete(run(app, rootClass, loop)))
