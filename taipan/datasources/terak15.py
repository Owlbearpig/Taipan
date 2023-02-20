from common import DataSet, DataSource, Q_, action
import asyncio
import socket
import base64
from common.traits import Quantity, DataSet as DataSetTrait
from traitlets import Bool, Unicode, observe, Integer
import numpy
from interfaces.scancontrolclient import QWebChannelWebSocketProtocol
from websockets import client
import enum

"""
1. Can laser and antenna voltage be enabled too?
2. What is the difference between pulseReady and displayPulseReady?
3. What are PulseFlags ?
"""


class ScanControlStatus(enum.IntEnum):
    Uninitialized = 0
    Initializing = 1
    Idle = 2
    Acquiring = 3
    Busy = 4
    Error = 5


class TeraK15(DataSource):
    status = Unicode(ScanControlStatus.Uninitialized.name, read_only=True).tag(name="System status", priority=0)
    acq_begin = Quantity(Q_(150, "ps")).tag(name="Start", priority=1)
    acq_end = Quantity(Q_(250, "ps")).tag(name="End", priority=2)
    acq_range = Quantity(Q_(100, "ps"), read_only=True).tag(name="Range", priority=3)
    acq_on = Bool(False, read_only=True).tag(name="Acquistion active")
    desiredAverages = Integer(1, min=1, max=30000).tag(name="Averages", priority=4)
    currentAverages = Integer(0, read_only=True).tag(name="Current averages", priority=5)
    acq_rate = Quantity(Q_(0, "Hz"), read_only=True).tag(name="Current rate", priority=7)
    requested_rate = Quantity(Q_(0, "Hz")).tag(name="Requested rate", priority=6)

    currentData = DataSetTrait(read_only=True).tag(name="Live data",
                                                   data_label="Amplitude",
                                                   axes_labels=["Time"])

    def __init__(self, name_or_ip=None, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.name_or_ip = name_or_ip
        self._setAveragesReachedFuture = asyncio.Future()

    async def __aenter__(self):
        await self._establish_connection()
        await self._single_update()
        await self._connect_signals()

    async def _establish_connection(self, port="8002"):
        print("Initializing scancontrol connection...")
        try:
            if self.name_or_ip is not None:
                socket.inet_aton(self.name_or_ip)
                self.name_or_ip = self.name_or_ip
        except OSError:
            pass

        self.port = port
        url = "ws://" + self.name_or_ip + ":" + self.port

        proto = await client.connect(url, create_protocol=QWebChannelWebSocketProtocol)
        await proto.webchannel

        self.scancontrol = proto.webchannel.objects["scancontrol"]
        print("Connected.")

    def status_changed(self, new_status):
        self.set_trait("status", ScanControlStatus(new_status).name)
        self.set_trait("acq_on", new_status == 3)

    def acq_rate_changed(self, new_val):
        self.set_trait("acq_rate", Q_(new_val, "Hz"))

    def acq_begin_changed(self, new_val):
        self.set_trait("acq_begin", Q_(new_val, "ps"))

    def acq_range_changed(self, new_val):
        self.set_trait("acq_range", Q_(new_val, "ps"))

    def acq_end_changed(self, new_val):
        self.set_trait("acq_end", Q_(new_val, "ps"))

    def _decodeData(self, data):
        return numpy.frombuffer(base64.b64decode(data), dtype=numpy.float64)

    def _decodeAmpArray(self, data):
        encAmpData = data["amplitude"]
        decAmpData = []
        for set in encAmpData:
            decAmpData.append(self._decodeData(set))

        data["amplitude"] = decAmpData
        return data

    def _onDisplayPulseReady(self, data):
        data = self._decodeAmpArray(data)
        if self.scancontrol.timeAxis is not None:
            decTimeAxis = self._decodeData(self.scancontrol.timeAxis)
            if len(data["amplitude"][0]) == len(decTimeAxis):
                data["timeaxis"] = decTimeAxis
                decTimeAxis = Q_(decTimeAxis, "ps")

                data = DataSet(Q_(data["amplitude"][0], "mV"), [decTimeAxis])

                self.set_trait("currentData", data)
                self.set_trait("currentAverages", min(self.currentAverages + 1,
                                                      self.desiredAverages))

                if (not self._setAveragesReachedFuture.done() and
                        self.currentAverages >= self.desiredAverages):
                    self._setAveragesReachedFuture.set_result(True)

    def _onPulseReady(self, data):
        data = self._decodeAmpArray(data)
        if self.scancontrol.timeAxis is not None:
            decTimeAxis = self._decodeData(self.scancontrol.timeAxis)
            if len(data["amplitude"][0]) == len(decTimeAxis):
                data["timeaxis"] = decTimeAxis
                decTimeAxis = Q_(decTimeAxis, "ps")

                data = DataSet(Q_(data["amplitude"][0], "mV"), [decTimeAxis])

                self.set_trait("currentData", data)
                self.set_trait("currentAverages", min(self.currentAverages + 1,
                                                      self.desiredAverages))

                if (not self._setAveragesReachedFuture.done() and
                        self.currentAverages >= self.desiredAverages):
                    self._setAveragesReachedFuture.set_result(True)

    async def _connect_signals(self):
        self.scancontrol.statusChanged.connect(self.status_changed)
        self.scancontrol.beginChanged.connect(self.acq_begin_changed)
        self.scancontrol.endChanged.connect(self.acq_end_changed)
        self.scancontrol.rangeChanged.connect(self.acq_range_changed)
        self.scancontrol.rateChanged.connect(self.acq_rate_changed)
        self.scancontrol.displayPulseReady.connect(self._onPulseReady)

    @observe("requested_rate")
    def _rate_changed(self, change):
        newVal = change["new"].to("Hz").magnitude

        async def _impl():
            await self.scancontrol.setRate(newVal)
            await self.reset_avg()

        self._loop.create_task(_impl())

    @observe("acq_begin")
    def _acq_begin_changed(self, change):
        newVal = change["new"].to("ps").magnitude

        async def _impl():
            await self.scancontrol.setBegin(newVal)
            await self.reset_avg()

        self._loop.create_task(_impl())

    @observe("acq_end")
    def _acq_end_changed(self, change):
        newVal = change["new"].to("ps").magnitude

        async def _impl():
            await self.scancontrol.setEnd(newVal)
            await self.reset_avg()

        self._loop.create_task(_impl())

    async def _single_update(self):
        scan_control = self.scancontrol

        self.set_trait("status", ScanControlStatus(scan_control.status).name)
        self.set_trait("acq_begin", Q_(scan_control.begin, "ps"))
        self.set_trait("acq_end", Q_(scan_control.end, "ps"))
        self.set_trait("acq_range", Q_(scan_control.range, "ps"))
        self.set_trait("acq_on", scan_control.status == 3)
        self.set_trait("desiredAverages", scan_control.desiredAverages)
        self.set_trait("currentAverages", scan_control.currentAverages)

    async def readDataSet(self):
        if not self.acq_on:
            raise Exception("Trying to read data from TeraK15 but acquisition is "
                            "turned off!")

        await self.reset_avg()
        success = await self._setAveragesReachedFuture
        if not success:
            raise Exception("Failed to reach the target averages value!")

        self._dataSetReady(self.currentData)
        return self.currentData

    @action("Start acquisition")
    async def start_acq(self):
        await self.reset_avg()
        await self.scancontrol.start()

    @action("Stop acquisition")
    async def stop_acq(self):
        await self.scancontrol.stop()

    @action("Reset average")
    async def reset_avg(self):
        await self.scancontrol.resetAveraging()
        self.set_trait("currentAverages", 0)
        if self._setAveragesReachedFuture.done():
            self._setAveragesReachedFuture = asyncio.Future()

    async def __aexit__(self, *args):
        print("Exiting")
        await super().__aexit__(*args)
