from common import DataSet, DataSource, Q_, action
import asyncio
from asyncioext import ensure_weakly_binding_future
import logging
import socket
import struct
import io
from common.traits import Quantity, DataSet as DataSetTrait
from traitlets import Bool, Float, Unicode, observe, Integer
import numpy as np
from threading import Thread
from multiprocessing import Process, Queue
from interfaces.scancontrolclient import ScanControlClient
from PyQt5.QtCore import pyqtSignal

def gotPulse(data):
    print('Got Pulse:')
    print(data['amplitude'][0])

class TeraK15(DataSource):
    #statusChanged = pyqtSignal(int)

    #acq_begin = Quantity(Q_(500, 'ps')).tag(name="Start", priority=0)
    #acq_range = Quantity(Q_(70, 'ps')).tag(name="Range", priority=1)
    #acq_on = Bool(False, read_only=True).tag(name="Acquistion active")
    #acq_avg = Integer(1, min=1, max=30000).tag(name="Averages", priority=2)
    #acq_current_avg = Integer(0, read_only=True).tag(name="Current averages", priority=3)

    currentData = DataSetTrait(read_only=True).tag(name="Live data",
                                                   data_label="Amplitude",
                                                   axes_labels=["Time"])

    def __init__(self, name_or_ip=None, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.name_or_ip = name_or_ip
        self.loop = loop

    def _status_changed(self, newStatus):
        pass
        #self.statusChanged.emit(newStatus)

    def connect_signals(self):
        self.ScanControl.statusChanged.connect(self._status_changed)

    async def __aenter__(self):
        print("Initializing terak15 ...")

        self.ip = None

        try:
            if self.name_or_ip is not None:
                socket.inet_aton(self.name_or_ip)
                self.ip = self.name_or_ip
        except OSError:
            pass

        client = ScanControlClient(loop=self.loop)
        await client.connect(host=self.ip)
        self.ScanControl = client.scancontrol

    @action("Start acquisition")
    async def start(self):
        await self.ScanControl.start()

    @action("Stop acquisition")
    async def stop(self):
        await self.ScanControl.stop()

    async def __aexit__(self, *args):
        print("Closing terak15")
        await super().__aexit__(*args)
