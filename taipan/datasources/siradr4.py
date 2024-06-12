import time

import numpy as np
import traitlets
import struct
from common import DataSource, action, ComponentBase, DataSet
from common.traits import DataSet as DataSetTrait, Quantity, Q_
from traitlets import Unicode, Integer, Bool, Enum, observe, Instance, All, Float
from asyncioext import threaded_async, ensure_weakly_binding_future
from serial import Serial
from threading import Lock
import logging
import asyncio
import enum
from multiprocessing import Process, Queue
from dummy import DummySerial

"""
# TODO
1. continuous update of I, ...
2. handle data frames
3. 

"""


class SerialConnection:
    def __init__(self, port, baudrate, enableDebug=True):
        # self.serial = DummySerial()
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
    serial_connection.flush()

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


def bin_str(x, zfill=0):
    return bin(x)[2:].zfill(zfill)


def bin_hex(b_, fix_len=8):
    return format(b_, '0' + str(fix_len) + 'X')


def twos_compl_hex_int(hex_str, str_len=4):
    number = int(hex_str, 16)

    # Check if the number is negative (if the most significant bit is 1)
    if number & (1 << (str_len * 4 - 1)):
        # Calculate the negative value using two's complement
        number = number - (1 << str_len * 4)

    return number


class SiRadBackend(ComponentBase):
    class SelfTrigDelay(enum.Enum):
        SelfTrigDelay_0ms = 0
        SelfTrigDelay_2ms = 1
        SelfTrigDelay_4ms = 2
        SelfTrigDelay_8ms = 3
        SelfTrigDelay_16ms = 4
        SelfTrigDelay_32ms = 5
        SelfTrigDelay_64ms = 6
        SelfTrigDelay_128ms = 7

    class CL(enum.Enum):
        DC_coupling = 0
        AC_coupling = 1

    class LOG(enum.Enum):
        log_mag = 0
        linear_mag = 1

    class FMT(enum.Enum):
        TL_mm_dist = 0
        TL_cm_dist = 1

    class LED(enum.Enum):
        off = 0
        first_target = 1

    class Protocol(enum.Enum):
        webGUI = 0
        TSV_output = 1
        BIN_output = 2

    class Gain(enum.Enum):
        zero = 0
        one = 1
        two = 2
        three = 3
        four = 4
        five = 5

    class SLF(enum.Enum):
        external_trig_mode = 0
        standard_mode = 1

    class CFAR(enum.Enum):
        CA_CFAR = 0
        GO_CFAR = 1
        SO_CFAR = 2

    class CFAR_Threshold(enum.Enum):
        CFAR_Threshold_0dB = 0
        CFAR_Threshold_2dB = 1
        CFAR_Threshold_4dB = 2
        CFAR_Threshold_6dB = 3
        CFAR_Threshold_8dB = 4
        CFAR_Threshold_10dB = 5
        CFAR_Threshold_12dB = 6
        CFAR_Threshold_14dB = 7
        CFAR_Threshold_16dB = 8
        CFAR_Threshold_18dB = 9
        CFAR_Threshold_20dB = 10
        CFAR_Threshold_22dB = 11
        CFAR_Threshold_24dB = 12
        CFAR_Threshold_26dB = 13
        CFAR_Threshold_28dB = 14
        CFAR_Threshold_30dB = 15

    class CFAR_Size(enum.Enum):
        CFAR_Size_0 = 0
        CFAR_Size_1 = 1
        CFAR_Size_2 = 2
        CFAR_Size_3 = 3
        CFAR_Size_4 = 4
        CFAR_Size_5 = 5
        CFAR_Size_6 = 6
        CFAR_Size_7 = 7
        CFAR_Size_8 = 8
        CFAR_Size_9 = 9
        CFAR_Size_10 = 10
        CFAR_Size_11 = 11
        CFAR_Size_12 = 12
        CFAR_Size_13 = 13
        CFAR_Size_14 = 14
        CFAR_Size_15 = 15

    class CFAR_GRD(enum.Enum):
        CFAR_GRD_0 = 0
        CFAR_GRD_1 = 1
        CFAR_GRD_2 = 2
        CFAR_GRD_3 = 3

    class Average_number(enum.Enum):
        Average_number_0 = 0
        Average_number_1 = 1
        Average_number_2 = 2
        Average_number_3 = 3

    class FFT_Size(enum.Enum):
        FFT_Size_32 = 0
        FFT_Size_64 = 1
        FFT_Size_128 = 2
        FFT_Size_256 = 3
        FFT_Size_512 = 4
        FFT_Size_1024 = 5
        FFT_Size_2048 = 6

    class DownSampling(enum.Enum):
        DownSampling_0 = 0
        DownSampling_1 = 1
        DownSampling_2 = 2
        DownSampling_4 = 3
        DownSampling_8 = 4
        DownSampling_16 = 5
        DownSampling_32 = 6
        DownSampling_64 = 7

    class RampCount(enum.Enum):
        RampCount_1 = 0
        RampCount_2 = 1
        RampCount_4 = 2
        RampCount_8 = 3
        RampCount_16 = 4
        RampCount_32 = 5
        RampCount_64 = 6
        RampCount_128 = 7

    class Samples(enum.Enum):
        Samples_32 = 0
        Samples_64 = 1
        Samples_128 = 2
        Samples_256 = 3
        Samples_512 = 4
        Samples_1024 = 5
        Samples_2048 = 6

    class ADC_ClkDiv(enum.Enum):
        ADC_ClkDiv_1800kSHz = 0
        ADC_ClkDiv_1000kSHz = 1
        ADC_ClkDiv_675kSHz = 2
        ADC_ClkDiv_397kSHz = 3
        ADC_ClkDiv_281_25kSHz = 4
        ADC_ClkDiv_218kSHz = 5
        ADC_ClkDiv_173kSHz = 6
        ADC_ClkDiv_55kSHz = 7

    error_messages = {0x1: 'Base frequency too low',
                      0x2: 'Base frequency too high',
                      0x4: 'Bandwith exceeds min frequency',
                      0x8: 'Bandwith exceeds max frequency',
                      0x20: 'Front end out of specification',
                      0x100: 'Minimum RF frequency not found',
                      0x200: "Maximum RF frequency not found",
                      0x400: "Lock loss",
                      0x1000: "Amplifier saturated",
                      0x10000: "Too many samples",
                      0x20000: "DC error",
                      }

    acq_on = Bool(False, read_only=True).tag(name="Acquistion active")

    # Error traits
    error_value = Unicode("", read_only=True).tag(name="Error Message", group="Error")
    flash_error = Bool(False, read_only=True).tag(name="Flash error", group="Error")
    processing_error = Bool(False, read_only=True).tag(name="Processing error", group="Error")
    baseband_error = Bool(False, read_only=True).tag(name="Baseband error", group="Error")
    pll_error = Bool(False, read_only=True).tag(name="PLL error", group="Error")
    frontend_error = Bool(False, read_only=True).tag(name="Frontend error", group="Error")
    crc_error = Bool(False, read_only=True).tag(name="CRC error", group="Error")

    # system and version information
    microcontroller_UID = Unicode(read_only=True)
    microcontroller_UID.tag(name="Microcontroller UID", group="System information")
    rfe_minfreq = Quantity(Q_(0, "GHz"), read_only=True)
    rfe_minfreq.tag(name="RFE min frequency", group="System information", priority=6)
    rfe_maxfreq = Quantity(Q_(0, "GHz"), read_only=True)
    rfe_maxfreq.tag(name="RFE max frequency", group="System information", priority=7)

    baseboard_id = Unicode(read_only=True, help="hallo").tag(name="Baseboard identifier", group="System information")
    ppl_chip_id = Unicode(read_only=True).tag(name="PPL chip identifier", group="System information")
    clk_chip_identifier = Unicode(read_only=True).tag(name="CLK chip identifier", group="System information")
    adc_operating_mode = Unicode(read_only=True).tag(name="ADC operating mode", group="System information")
    rfe_chip_identifier = Unicode(read_only=True).tag(name="RFE chip identifier", group="System information")
    firmware_version = Unicode(read_only=True).tag(name="Firmware version", group="System information")
    protocol_version = Unicode(read_only=True).tag(name="Protocol version", group="System information")

    format_ = Enum(FMT, FMT.TL_mm_dist, read_only=True).tag(name="Format", group="Status information")
    gain = Quantity(Q_(0, "dB"), read_only=True).tag(name="Gain", group="Status information")
    accuracy = Quantity(Q_(0, "mm"), read_only=True).tag(name="Accuracy", group="Status information")
    max_range = Quantity(Q_(0, "mm"), read_only=True).tag(name="Max range", group="Status information")
    ramp_time = Quantity(Q_(0, "us"), read_only=True).tag(name="Ramp time", group="Status information")
    bandwidth = Quantity(Q_(0, "GHz"), read_only=True).tag(name="Bandwidth", group="Status information")
    time_diff = Quantity(Q_(0, "ms"), read_only=True).tag(name="Time difference", group="Status information")
    widener = Unicode(read_only=True, default_value=14 * "_").tag(name="", group="Status information")

    # system config traits
    self_trig_delay = Enum(SelfTrigDelay, SelfTrigDelay.SelfTrigDelay_0ms)
    self_trig_delay.tag(name="Self trigger delay", group="System config")
    log_magnitude = Enum(LOG, LOG.log_mag).tag(name="Log magnitude", group="System config")
    led_toggle = Enum(LED, LED.first_target).tag(name="LED toggle", group="System config")
    data_fmt = Enum(FMT, FMT.TL_mm_dist).tag(name="Output data unit", group="System config")
    baseband_amp_coupling = Enum(CL, CL.DC_coupling).tag(name="Baseband amplifier coupling", group="System config")
    auto_gain_control = Bool(False).tag(name="Auto gain enabled", group="System config")
    protocol = Enum(Protocol, Protocol.webGUI, read_only=True).tag(name="Data protocol type", group="System config")
    manual_gain = Enum(Gain, Gain.five).tag(name="Gain setting", group="System config")
    trigger_mode = Enum(SLF, SLF.standard_mode).tag(name="Trigger mode", group="System config")
    pre_trigger_en = Bool(False).tag(name="Enable pre-trigger", group="System config")

    # connection should not be changed while in use
    ser1_en = Bool(False, read_only=True).tag(name="Enable 1x UART", group="System config")
    ser2_en = Bool(True, read_only=True).tag(name="Enable 2x UART", group="System config")

    # not in WebGUI protocol
    raw_df = Bool(False, read_only=True).tag(name="Raw ADC", group="Enabled data frames")
    cpl_df = Bool(False, read_only=True).tag(name="Complex FFT", group="Enabled data frames")

    p_df = Bool(True).tag(name="Phase", group="Enabled data frames")
    r_df = Bool(True).tag(name="Magnitude", group="Enabled data frames")
    c_df = Bool(True).tag(name="CFAR", group="Enabled data frames")
    st_df = Bool(True).tag(name="Status", group="Enabled data frames")
    err_df = Bool(True).tag(name="Error", group="Enabled data frames")

    # data acquisition for target list frames not implemented
    tl_df = Bool(False, read_only=True).tag(name="Target list", group="Enabled data frames")

    # radar front end traits
    frontend_base_freq = Quantity(Q_(295, "GHz"), min=Q_(0, "GHz"), max=Q_(int(2.5e-4 * 2 ** 21), "GHz"), priority=1)
    frontend_base_freq.tag(name="Base frequency", group="PLL and front end configuration")

    # PLL configuration
    frontend_bandwidth = Quantity(Q_(22, "GHz"), min=Q_(-2 ** (16 - 1) * 2e-3, "GHz"),
                                  max=Q_(2 ** (16 - 1) * 2e-3, "GHz"), help="Is added to base frequency",
                                  priority=2)
    frontend_bandwidth.tag(name="Bandwidth", group="PLL and front end configuration")

    # Baseband and processing configuration
    windowing_en = Bool(True).tag(name="Windowing enabled", group="Baseband configuration")
    fir_filter_en = Bool(False).tag(name="FIR filter enabled", group="Baseband configuration")
    dc_cancellation_en = Bool(True).tag(name="DC cancellation enabled", group="Baseband configuration")
    cfar_operator = Enum(CFAR, CFAR.CA_CFAR).tag(name="CFAR operator", group="Baseband configuration")
    cfar_threshold = Enum(CFAR_Threshold, CFAR_Threshold.CFAR_Threshold_16dB)
    cfar_threshold.tag(name="CFAR Threshold", group="Baseband configuration")
    cfar_size = Enum(CFAR_Size, CFAR_Size.CFAR_Size_10)
    cfar_size.tag(name="CFAR Size", group="Baseband configuration")
    cfar_guard = Enum(CFAR_GRD, CFAR_GRD.CFAR_GRD_1)
    cfar_guard.tag(name="CFAR Guard", group="Baseband configuration")
    fft_size = Enum(FFT_Size, FFT_Size.FFT_Size_512)
    fft_size.tag(name="FFT points", group="Baseband configuration")
    downsampling = Enum(DownSampling, DownSampling.DownSampling_0)
    downsampling.tag(name="Down sampling factor", group="Baseband configuration")
    ramp_count = Enum(RampCount, RampCount.RampCount_1)
    ramp_count.tag(name="Number of ramps", group="Baseband configuration")
    sample_count = Enum(Samples, Samples.Samples_128)
    sample_count.tag(name="Number of samples", group="Baseband configuration")
    average_n = Enum(Average_number, Average_number.Average_number_3)
    average_n.tag(name="FFT averages", group="Baseband configuration")
    adc_clkdiv = Enum(ADC_ClkDiv, ADC_ClkDiv.ADC_ClkDiv_397kSHz)
    adc_clkdiv.tag(name="ADC ClkDiv", group="Baseband configuration")

    def __init__(self, port, baudrate, loop):
        super().__init__("Config", loop)
        self.port = port
        self.baudrate = baudrate

        self.s_config_trait_groups = ["System config", "Enabled data frames"]
        self.config_observers()
        self.datasetQueue = Queue()
        self.config_changed = False

    async def __aenter__(self):
        await super().__aenter__()
        await self.device_init()

        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self.connectionProcess.terminate()
        self.frameReader.cancel()

    def config_observers(self):
        s_config_traits = []
        for trait_grp in self.s_config_trait_groups:
            s_config_traits.extend(self.traits(group=trait_grp).keys())

        self.observe(self.update_s_config, s_config_traits)

        pll_rfe_config_traits = list(self.traits(group="PLL and front end configuration").keys())
        self.observe(self.update_pf_config, pll_rfe_config_traits)

        b_config_traits = list(self.traits(group="Baseband configuration").keys())
        self.observe(self.update_b_config, b_config_traits)

    async def device_init(self):
        self.frameQueue = Queue()
        self.commandQueue = Queue()
        self.connectionProcess = Process(target=device_interface, args=(self.frameQueue, self.commandQueue,
                                                                        self.port, self.baudrate))
        self.connectionProcess.start()

        self.frameReader = ensure_weakly_binding_future(self.read_frame_from_queue)

        self.update_s_config()
        self.update_pf_config()
        self.update_b_config()

    def update_s_config(self, change=None):
        self.config_changed = True
        df_traits = [self.err_df, self.st_df, self.tl_df, self.c_df,
                     self.r_df, self.p_df, self.raw_df, self.cpl_df]

        config_str = ""
        config_str += bin_str(self.self_trig_delay.value, zfill=3)
        config_str += bin_str(self.baseband_amp_coupling.value)
        config_str += bin_str(self.log_magnitude.value)
        config_str += bin_str(self.data_fmt.value)
        config_str += "0" + bin_str(self.led_toggle.value) + 4 * "0"
        config_str += bin_str(self.protocol.value, zfill=2)
        config_str += bin_str(self.auto_gain_control)
        config_str += bin_str(self.manual_gain.value, zfill=3)
        config_str += bin_str(self.ser2_en) + bin_str(self.ser1_en)
        config_str += "".join([bin_str(df_trait) for df_trait in df_traits]) + 2 * "0"
        config_str += bin_str(self.trigger_mode.value) + bin_str(self.pre_trigger_en)

        config_str = bin_hex(int(config_str, 2))

        asyncio.create_task(self.send_command("!S" + config_str))

    def update_pf_config(self, change=None):
        self.config_changed = True
        # applies both configs on each call
        # f config
        config_str = 4 * "0" + "1" + 7 * "0"  # 120 GHz TODO value unclear of "reserved" part for 300 GHz system
        config_str += bin_str(int(self.frontend_base_freq.magnitude * 1e6 / 250), zfill=21)

        config_str = bin_hex(int(config_str, 2))

        asyncio.create_task(self.send_command("!F" + config_str))

        # p config
        val = int(self.frontend_bandwidth.magnitude * 1e3 / 2)
        config_str = 16 * "0"
        if val < 0:
            val = (1 << 16) + val
            bin_str_ = bin_str(val, zfill=16)
        else:
            bin_str_ = bin_str(val, zfill=16)
        config_str += bin_str_

        config_str = bin_hex(int(config_str, 2))

        asyncio.create_task(self.send_command("!P" + config_str))

    def update_b_config(self, change=None):
        self.config_changed = True
        config_str = ""
        config_str += bin_str(self.windowing_en)
        config_str += bin_str(self.fir_filter_en)
        config_str += bin_str(self.dc_cancellation_en)
        config_str += bin_str(self.cfar_operator.value, zfill=2)
        config_str += bin_str(self.cfar_threshold.value, zfill=4)
        config_str += bin_str(self.cfar_size.value, zfill=4)
        config_str += bin_str(self.cfar_guard.value, zfill=2)
        config_str += bin_str(self.average_n.value, zfill=2)
        config_str += bin_str(self.fft_size.value, zfill=3)
        config_str += bin_str(self.downsampling.value, zfill=3)
        config_str += bin_str(self.ramp_count.value, zfill=3)
        config_str += bin_str(self.sample_count.value, zfill=3)
        config_str += bin_str(self.adc_clkdiv.value, zfill=3)

        config_str = bin_hex(int(config_str, 2))

        asyncio.create_task(self.send_command("!B" + config_str))

    async def read_frame_from_queue(self):
        frame_handler_map = {b"R": self.parse_data_frame,
                             b"P": self.parse_data_frame,
                             b"C": self.parse_data_frame,
                             b"T": self.parse_target_list_frame,  # TODO implement
                             b"U": self.parse_update_frame,
                             b"V": self.parse_version_frame,
                             b"I": self.parse_info_frame,
                             b"E": self.parse_error_frame}

        while True:
            # yield control to the event loop once
            await asyncio.sleep(0)
            while not self.frameQueue.empty():
                frame = self.frameQueue.get()
                frame_identifier = frame[1:2]
                if frame_identifier in frame_handler_map:
                    try:
                        frame_handler_map[frame_identifier](frame)
                    except Exception as e:
                        logging.info(e)
                    # print(frame, self.frameQueue.qsize(), "in frame queue")

    def parse_version_frame(self, frame):
        def dict_lookup(dict_, key):
            try:
                return dict_[key]
            except KeyError:
                return key

        i0, i1 = 7, 9
        frame_parts = []
        for i in range(8):
            chunk_len = int(frame[i0:i1], 16)
            section_end = i1 + chunk_len
            frame_parts.append(frame[i1:section_end])
            i0, i1 = section_end + 1, section_end + 3

        baseboards = {b'EA': "SiRad Easy"}
        pll_chips = {b'59': "ADF4159"}
        rfe_types = {b'024_x6': "TRX_024_046", b'120_01': "TRX_120_001", b'120_02': "TRX_120_002",
                     b'120_45': "TRX_120_045", b'300_42': "TRX_300_042"}

        self.set_trait("baseboard_id", dict_lookup(baseboards, frame_parts[1]))
        self.set_trait("ppl_chip_id", dict_lookup(pll_chips, frame_parts[2]))
        self.set_trait("clk_chip_identifier", frame_parts[3])
        adc_operating_mode = "Interleaved" if frame_parts[4] == b'I' else "Non-interleaved"
        self.set_trait("adc_operating_mode", adc_operating_mode)
        self.set_trait("rfe_chip_identifier", dict_lookup(rfe_types, frame_parts[5]))
        self.set_trait("firmware_version", frame_parts[6])
        self.set_trait("protocol_version", frame_parts[7])

    def parse_info_frame(self, frame, *args):
        ic_id = frame[2:26]

        rfe_min_freq = 1e-3 * int(frame[28:33], 16)  # TODO check conversion factor (GHz)
        rfe_max_freq = 1e-3 * int(frame[33:38], 16)

        self.set_trait("microcontroller_UID", ic_id)
        self.set_trait("rfe_minfreq", Q_(rfe_min_freq, "GHz"))
        self.set_trait("rfe_maxfreq", Q_(rfe_max_freq, "GHz"))

    def parse_error_frame(self, frame):
        is_detailed = len(frame) > 8
        error_flags = frame[2:len(frame) - 2]
        error_code = int(error_flags, 16)
        if not error_code:
            self.set_trait("error_value", "")

        if not is_detailed:
            self.set_trait("crc_error", bool(error_code & (1 << 0)))
            self.set_trait("frontend_error", bool(error_code & (1 << 1)))
            self.set_trait("pll_error", bool(error_code & (1 << 2)))
            self.set_trait("baseband_error", bool(error_code & (1 << 3)))
            self.set_trait("processing_error", bool(error_code & (1 << 4)))
            self.set_trait("flash_error", bool(error_code & (1 << 5)))
        else:
            for k in SiRadBackend.error_messages:
                if k & error_code:
                    msg = f"{SiRadBackend.error_messages[k]}"
                    logging.info(msg)
                    self.set_trait("error_value", msg)
            if error_code:
                s = bin_str(error_code, zfill=32)
                logging.info("Error code: " + " ".join([s[4 * i:4 * (i + 1)] for i in range(32)]))

    def parse_update_frame(self, frame):
        format_field = int(frame[2:3], 16)
        gain = Q_(-140 + ord(frame[3:4]), "dB")
        accuracy = Q_(0.1 * int(frame[4:8], 16), "mm")
        max_range = Q_(int(frame[8:12], 16), "mm")  # TODO check unit
        ramp_time = Q_(int(frame[12:16], 16), "us")
        bandwidth = Q_(2e-3 * twos_compl_hex_int(frame[16:20]), "GHz")
        time_diff = Q_(0.01 * int(frame[20:24], 16), "ms")

        self.set_trait("format_", SiRadBackend.FMT(format_field))
        self.set_trait("gain", gain)
        self.set_trait("accuracy", accuracy)
        self.set_trait("max_range", max_range)
        self.set_trait("ramp_time", ramp_time)
        self.set_trait("bandwidth", bandwidth)
        self.set_trait("time_diff", time_diff)

    def parse_target_list_frame(self, frame):
        pass

    def parse_data_frame(self, frame):
        if not self.acq_on:
            return

        frame_id = frame[1:2]
        if frame_id not in [b'R', b'C', b'P']:
            return

        size = int(frame[2:6], 16)

        data_part = frame[14:14 + size]
        format_str = 'B' * size

        if frame_id in [b'R', b'C']:
            data_arr = np.array(struct.unpack(format_str, data_part)) - 173
            data = Q_(data_arr, "dB")
        else:
            data_arr = np.pi * (np.array(struct.unpack(format_str, data_part)) - 143) / 110
            data = Q_(data_arr, "rad")

        freq = self.frontend_base_freq.magnitude
        freqbandwidth = self.frontend_bandwidth.magnitude

        freqarr = Q_(np.linspace(freq, freq + freqbandwidth, size), "GHz")

        dataset = DataSet(data, [freqarr])
        self.datasetQueue.put((frame_id, dataset))

    async def send_command(self, command):
        self.commandQueue.put(command)

    @action("Detailed error report", group="Special functions")
    def error_report(self):
        asyncio.create_task(self.send_command("!E"))

    @action("Get system info", group="Special functions")
    def system_info(self):
        asyncio.create_task(self.send_command("!I"))

    @action("Frequency scan", group="Special functions")
    def freq_scan(self):
        asyncio.create_task(self.send_command("!J"))

    @action("Set to max bandwidth", group="Special functions")
    def set_to_max_bandwidth(self):
        asyncio.create_task(self.send_command("!K"))

    @action("Get version", group="Special functions")
    def get_version(self):
        asyncio.create_task(self.send_command("!V"))

    @action("Send pre-trigger", group="Triggering")
    def pre_trigger(self):
        asyncio.create_task(self.send_command("!L"))

    @action("Send main trigger", group="Triggering")
    def main_trigger(self):
        asyncio.create_task(self.send_command("!M"))

    @action("Send both triggers", group="Triggering")
    def both_triggers(self):
        asyncio.create_task(self.send_command("!N"))


class SiRadR4(DataSource):
    current_amp_data = DataSetTrait(read_only=True).tag(name="Live amplitude data",
                                                        data_label="Amplitude",
                                                        axes_labels=["Frequency"],
                                                        simple_plot=True)
    current_phi_data = DataSetTrait(read_only=True).tag(name="Live phase data",
                                                        data_label="Phase",
                                                        axes_labels=["Frequency"],
                                                        simple_plot=True)
    current_cfar_data = DataSetTrait(read_only=True).tag(name="Live CFAR data",
                                                         data_label="CFAR",
                                                         axes_labels=["Frequency"],
                                                         simple_plot=True)
    backend = Instance(SiRadBackend)

    acq_on = Bool(False, read_only=True).tag(name="Acquistion active")

    acq_avg = Integer(100, min=1, max=30000).tag(name="Averages", priority=2)
    acq_current_avg = Integer(0, read_only=True).tag(name="Current averages", priority=3)

    def __init__(self, port=None, baudrate=230400, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self.backend = SiRadBackend(port, baudrate, loop)
        self.dataset_checker = ensure_weakly_binding_future(self.get_dataset)
        self._setAveragesReachedFuture = asyncio.Future()
        self.dataset_buffer = {b'R': [], b'P': [], b'C': []}

    async def __aenter__(self):
        await super().__aenter__()

        return self

    async def __aexit__(self, *args):
        self.dataset_checker.cancel()
        await super().__aexit__(*args)

    async def get_dataset(self):
        try:
            while True:
                await asyncio.sleep(0)
                if not self.backend.acq_on:
                    continue

                if self.backend.config_changed:
                    await self.reset_avg()
                    self.backend.config_changed = False
                if not self.backend.datasetQueue.empty():
                    frame_id, new_dataset = self.backend.datasetQueue.get()
                    buffer = self.dataset_buffer[frame_id]
                    buffer.append(new_dataset.data.magnitude)

                    # maybe faster with this extra delete of only the first element
                    if len(buffer) > self.acq_avg:
                        del buffer[0]
                    # reduce buffer to set avg size (important when average size is reduced by hand)
                    if len(buffer) > self.acq_avg + 1:
                        del buffer[:-self.acq_avg]

                    dataset_average = sum(buffer) / len(buffer)

                    unit = new_dataset.data.units
                    new_dataset.data = Q_(dataset_average, unit)
                    new_dataset.dataType = chr(frame_id[0])
                    if frame_id == b'R':
                        self.set_trait("current_amp_data", new_dataset)
                    elif frame_id == b'P':
                        self.set_trait("current_phi_data", new_dataset)
                    elif frame_id == b'C':
                        self.set_trait("current_cfar_data", new_dataset)
                    elif frame_id == b'T':
                        pass
                    else:
                        pass

                    self.set_trait('acq_current_avg', len(buffer))
                    if (not self._setAveragesReachedFuture.done() and
                            self.acq_current_avg >= self.acq_avg):
                        self._setAveragesReachedFuture.set_result(True)
        except Exception as e:
            logging.info(e)

    @action("Start acquisition")
    def start_acq(self):
        self.set_trait("acq_on", True)
        self.backend.set_trait("acq_on", True)

    @action("Stop acquisition")
    def stop_acq(self):
        self.set_trait("acq_on", False)
        self.backend.set_trait("acq_on", False)

    async def readDataSet(self):
        if not self.acq_on:
            raise Exception("Trying to read data but acquisition is "
                            "turned off!")

        await self.reset_avg()
        success = await self._setAveragesReachedFuture
        if not success:
            raise Exception("Failed to reach the target averages value!")

        active_datasets = []
        if self.backend.r_df:
            active_datasets.append(self.current_amp_data)
        if self.backend.p_df:
            active_datasets.append(self.current_phi_data)
        if self.backend.c_df:
            active_datasets.append(self.current_cfar_data)

        for ds in active_datasets:
            self._dataSetReady(ds)

        return active_datasets

    @action("Reset average")
    async def reset_avg(self):
        self.set_trait('acq_current_avg', 0)
        if self._setAveragesReachedFuture.done():
            self._setAveragesReachedFuture = asyncio.Future()
        self.dataset_buffer = {b'R': [], b'P': [], b'C': []}

