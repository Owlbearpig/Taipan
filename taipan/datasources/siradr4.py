import time

from common import DataSource, action
from common.traits import DataSet as DataSetTrait
from common.traits import Quantity, Q_
from traitlets import Unicode, Integer, Bool, Enum
from asyncioext import threaded_async, ensure_weakly_binding_future
from serial import Serial
from threading import Lock
import logging
import asyncio
import enum
from multiprocessing import Process, Queue


class SerialConnection:
    def __init__(self, port, baudrate, enableDebug=True):
        self.serial = Serial()
        self.port = port
        self.baudrate = baudrate
        self.timeout = None
        self._lock = Lock()
        self.enableDebug = enableDebug

    def open(self):
        """ Opens the Connection, potentially closing an old Connection
        """
        self.close()
        self.serial.port = self.port
        self.serial.baudrate = self.baudrate
        self.serial.timeout = self.timeout
        self.serial.open()

    def close(self):
        """ Closes the Connection.
        """
        if self.serial.isOpen():
            self.serial.close()

    def send(self, command, *args):
        with self._lock:
            # convert `command` to a bytearray
            if isinstance(command, str):
                command = bytearray(command, 'ascii')
            else:
                command = bytearray(command)

            for arg in args:
                if isinstance(arg, float):
                    command += b' %.6f' % arg
                else:
                    command += b' %a' % arg

            command += b'\r\n'

            if self.enableDebug:
                logging.info(str(command))

            self.serial.write(command)

    def read(self, bytes_=None):
        if bytes_:
            return self.serial.read(bytes_)

        return self.serial.readline()

    def flush(self):
        self.serial.flush()


def device_interface(frame_queue, command_queue, port, baudrate):
    serial_connection = SerialConnection(port, baudrate)
    serial_connection.timeout = 0.01
    serial_connection.open()

    while True:
        while not command_queue.empty():
            new_command = command_queue.get()
            serial_connection.send(new_command)

        frame = b''
        while True:
            if frame[-2:] == b'\r\n':
                frame_queue.put(frame)
                break
            frame += serial_connection.read(1)
            if not frame:
                break


class SiRadR4(DataSource):
    class SelfTrigDelay(enum.Enum):
        SelfTrigDelay_2ms = 0
        SelfTrigDelay_4ms = 1
        SelfTrigDelay_8ms = 2
        SelfTrigDelay_16ms = 3
        SelfTrigDelay_32ms = 4
        SelfTrigDelay_64ms = 5
        SelfTrigDelay_128ms = 6
        SelfTrigDelay_256ms = 7

    class ErrorBits(enum.Enum):
        CRC = 0x1
        RFE = 0x2
        PLL = 0x4
        BB = 0x8
        PRC = 0x10
        crc = 0x100
        rfe = 0x200
        pll = 0x400
        bb = 0x800
        prc = 0x1000

    error_messages = {0x1: 'temporary errors in the UART transmission CRC checksum are indicated by this bit',
                      0x2: 'temporary radar frontend configuration errors are indicated by this bit',
                      0x4: 'temporary PLL configuration errors are indicated',
                      0x8: 'temporary baseband processing errors will be indicated with this bit',
                      0x10: 'temporary errors in the signal processing will be indicated by this bit',
                      0x100: 'persistent errors in the UART transmission CRC checksum are indicated by this bit',
                      0x200: "persistent radar frontend configuration errors are indicated by this bit",
                      0x400: "persistent PLL configuration errors are indicated",
                      0x800: "persistent baseband processing errors will be indicated with this bit",
                      0x1000: "persistent errors in the signal processing will be indicated by this bit"}

    currentData = DataSetTrait(read_only=True).tag(name="Live data",
                                                   data_label="Amplitude",
                                                   axes_labels=["Time"])

    microcontroller_UID = Unicode(read_only=True).tag(name="Microcontroller UID", group="System information")
    rfe_minfreq = Quantity(Q_(0, "MHz"), read_only=True).tag(name="RFE min frequency", group="System information")
    rfe_maxfreq = Quantity(Q_(0, "MHz"), read_only=True).tag(name="RFE max frequency", group="System information")

    format_ = Integer(read_only=True).tag(name="Format", group="Status information")
    gain = Integer(read_only=True).tag(name="Gain", group="Status information")
    accuracy = Integer(read_only=True).tag(name="Accuracy", group="Status information")
    max_range = Integer(read_only=True).tag(name="Max range", group="Status information")
    ramp_time = Quantity(Q_(0, "us"), read_only=True).tag(name="Ramp time", group="Status information")
    bandwidth = Quantity(Q_(0, "MHz"), read_only=True).tag(name="Bandwidth", group="Status information")
    time_diff = Integer(read_only=True).tag(name="Time difference", group="Status information")

    en_status_frames = Bool(True).tag(name="Enable status frames", group="System config")
    enable_led = Bool(True).tag(name="Enable LED", group="System config")
    self_trig_delay = Enum(SelfTrigDelay, SelfTrigDelay.SelfTrigDelay_8ms).tag(name="Self trig delay",
                                                                               group="System config")

    error_value = Unicode("", read_only=True).tag(name="Error Value", group="ERROR")

    acq_on = Bool(False, read_only=True).tag(name="Acquistion active")

    def __init__(self, port=None, baudrate=230400, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.port = port
        self.baudrate = baudrate

        self.single_update = True

    async def __aenter__(self):
        await super().__aenter__()
        await self.device_init()

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self.connectionProcess.terminate()
        self.frameReader.cancel()

    async def device_init(self):
        self.frameQueue = Queue()
        self.commandQueue = Queue()
        self.connectionProcess = Process(target=device_interface, args=(self.frameQueue, self.commandQueue,
                                                                        self.port, self.baudrate))
        self.connectionProcess.start()

        self.frameReader = ensure_weakly_binding_future(self.readFrameFromQueue)

        await asyncio.create_task(self.send_command("!P00004E20"))  # p_config
        await asyncio.create_task(self.send_command("!BA453C013"))  # b_config
        # await asyncio.create_task(self.send("!S00013A08"))  # s_config
        # await asyncio.create_task(self.send("!F0201DC90"))
        # await asyncio.create_task(self.send_command("!S01016F80"))  # s_config # ext trig
        await asyncio.create_task(self.send_command("!S01016F82"))  # s_config # self trig

        await asyncio.create_task(self.send_command("!J"))  # auto detect frequency

    # observe traits -> on change assemble new config commands and put in queue

    async def readFrameFromQueue(self):
        while True:
            # yield control to the event loop once
            await asyncio.sleep(0)

            while not self.frameQueue.empty():
                # await asyncio.sleep(1)
                frame = self.frameQueue.get()
                print(frame, self.frameQueue.qsize())

    def handle_error_frame(self, error_frame):
        pass

    def distribute_frames(self, frame):
        pass

    async def send_command(self, command):
        self.commandQueue.put(command)

    def error_occured(self, error):
        for b in SiRadR4.ErrorBits:
            if bool(error & b.value):
                logging.info(SiRadR4.error_messages[b.value])

    def parse_frame(self, frame):
        ident = frame[1]
        data = frame[2:]

    @action("Start acquisition")
    def start_acq(self):
        self.set_trait("acq_on", True)
        asyncio.create_task(self.send_command("!S01016F80"))  # s_config # ext trig

    @action("Stop acquisition")
    def stop_acq(self):
        self.set_trait("acq_on", False)

    @action("Trigger")
    def trigger(self):
        asyncio.create_task(self.send_command("!M"))
