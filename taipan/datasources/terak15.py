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


def gotPulse(data):
    print('Got Pulse:')
    print(data['amplitude'][0])

class TeraK15(DataSource):

    def __init__(self, name_or_ip=None, objectName=None, loop=None):
        super().__init__(objectName, loop)

    client = ScanControlClient()
    client.connect(host="192.168.134.80")
    ScanControl = client.scancontrol

    print(dir(ScanControl))
    print(ScanControl)
    ScanControl.pulseReady.connect(gotPulse)
    #client.loop.run_until_complete(ScanControl.start())
    #client.loop.run_forever()


terak15 = TeraK15()
