from common import DataSource, action
from common.traits import DataSet as DataSetTrait
from common.traits import Quantity, Q_
from traitlets import Unicode, Integer, Bool, Enum
from asyncioext import threaded_async, ensure_weakly_binding_future
import serial
from serial import Serial
from threading import Lock
import logging
import asyncio
import enum



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

    def __init__(self, port=None, baudrate=230400, enableDebug=False, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.port = port
        self.baudrate = baudrate
        self.serial = Serial()
        self._lock = Lock()
        self.enableDebug = enableDebug  # does logging.info(str(command)) before serial.write(command)
        self._statusUpdateFuture = ensure_weakly_binding_future(self.contStatusUpdate)


    async def __aenter__(self):
        await super().__aenter__()
        self.open()

        await asyncio.create_task(self.send("!P00004E20"))  # p_config
        await asyncio.create_task(self.send("!BA453C013"))  # b_config
        # await asyncio.create_task(self.send("!S00013A08"))  # s_config
        # await asyncio.create_task(self.send("!F0201DC90"))
        await asyncio.create_task(self.send("!S01016F80"))  # s_config

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self.close()

    def handle_error_frame(self, error_frame):
        pass

    def distribute_frames(self, frame):
        pass

    def open(self):
        """ Opens the Connection, potentially closing an old Connection
        """
        self.close()
        self.serial.port = self.port
        self.serial.baudrate = self.baudrate
        self.serial.stopbits = serial.STOPBITS_ONE
        self.serial.open()

    def close(self):
        """ Closes the Connection.
        """
        if self.serial.isOpen():
            self.serial.close()

    async def statusUpdate(self):
        # self.serial.flush()
        # status = int(await self.query('*STB?'))
        ret = self.serial.readline()
        return ret

    def error_occured(self, error):
        for b in SiRadR4.ErrorBits:
            if bool(error & b.value):
                logging.info(SiRadR4.error_messages[b.value])

    @threaded_async
    def read(self):
        return self.serial.readline()

    async def contStatusUpdate(self):
        while True:
            await asyncio.sleep(0.01)
            ret = self.serial.readline()
            print(ret)

    def parse_frame(self, frame):
        ident = frame[1]
        data = frame[2:]

    @threaded_async
    def send(self, command, *args):
        """ Send a command over the Connection. If the command is a request,
        returns the reply.

        Parameters
        ----------
        command (convertible to bytearray) : The command to be sent.

        *args : Arguments to the command.
        """

        with self._lock:
            # convert `command` to a bytearray
            if isinstance(command, str):
                command = bytearray(command, 'ascii')
            else:
                command = bytearray(command)

            isRequest = command[-1] == ord(b'?')

            for arg in args:
                if isinstance(arg, float):
                    command += b' %.6f' % arg
                else:
                    command += b' %a' % arg

            command += b'\r\n'

            if self.enableDebug:
                logging.info(str(command))

            self.serial.write(command)

            # no request -> no reply. just return.
            if not isRequest:
                return

            # read reply. lines ending with ' \n' are part of a multiline
            # reply.
            replyLines = []
            while len(replyLines) == 0 or replyLines[-1][-2:] == ' \n':
                replyLines.append(self.serial.readline())

            return b''.join(replyLines)

    @action("Start acquisition")
    def start_acq(self):
        pass

    @action("Stop acquisition")
    def stop_acq(self):
        pass
