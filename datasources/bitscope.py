# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2017 Arno Rehn <arno@arnorehn.de>

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

from serial_asyncio import SerialTransport, create_serial_connection
import numpy as np
import asyncio
import binascii
import struct
import enum
from collections import deque

class Registers:
    vrTriggerLogic = (0x05, 1)
    vrTriggerMask = (0x06, 1)
    vrSpockOption = (0x07, 1)
    vrSampleAddress = (0x08, 3)
    vrSampleCounter = (0x0b, 3)
    vrTriggerIntro = (0x32, 2)
    vrTriggerOutro = (0x34, 2)
    vrTriggerValue = (0x44, 2)
    vrTriggerTime = (0x40, 4)
    vrClockTicks = (0x2e, 2)
    vrClockScale = (0x14, 2)
    vrTraceOption = (0x20, 1)
    vrTraceMode = (0x21, 1)
    vrTraceIntro = (0x26, 2)
    vrTraceDelay = (0x22, 4)
    vrTraceOutro = (0x2a, 2)
    vrTimeout = (0x2c, 2)
    vrPrelude = (0x3a, 2)
    vrBufferMode = (0x31, 1)
    vrDumpMode = (0x1e, 1)
    vrDumpChan = (0x30, 1)
    vrDumpSend = (0x18, 2)
    vrDumpSkip = (0x1a, 2)
    vrDumpCount = (0x1c, 2)
    vrDumpRepeat = (0x16, 2)
    vrStreamIdent = (0x36, 1)
    vrStampIdent = (0x3c, 1)
    vrAnalogEnable = (0x37, 1)
    vrDigitalEnable = (0x38, 1)
    vrSnoopEnable = (0x39, 1)
    vpCmd = (0x46, 1)
    vpMode = (0x47, 1)
    vpOption = (0x48, 2)
    vpSize = (0x4a, 2)
    vpIndex = (0x4c, 2)
    vpAddress = (0x4e, 2)
    vpClock = (0x50, 2)
    vpModulo = (0x52, 2)
    vpLevel = (0x54, 2)
    vpOffset = (0x56, 2)
    vpMask = (0x58, 2)
    vpRatio = (0x5a, 4)
    vpMark = (0x5e, 2)
    vpSpace = (0x60, 2)
    vpRise = (0x82, 2)
    vpFall = (0x84, 2)
    vpControl = (0x86, 1)
    vpRise2 = (0x88, 2)
    vpFall2 = (0x8a, 2)
    vpControl2 = (0x8c, 1)
    vpRise3 = (0x8e, 2)
    vpFall3 = (0x90, 2)
    vpControl3 = (0x92, 1)
    vrBaudRate = (0x3f, 1)
    vrConverterLo = (0x64, 2)
    vrConverterHi = (0x66, 2)
    vrTriggerLevel = (0x68, 2)
    vrLogicControl = (0x74, 1)
    vrRest = (0x78, 2)
    vrKitchenSinkA = (0x7b, 1)
    vrKitchenSinkB = (0x7c, 1)
    vpMap0 = (0x94, 1)
    vpMap1 = (0x95, 1)
    vpMap2 = (0x96, 1)
    vpMap3 = (0x97, 1)
    vpMap4 = (0x98, 1)
    vpMap5 = (0x99, 1)
    vpMap6 = (0x9a, 1)
    vpMap7 = (0x9b, 1)
    vrMasterClockN = (0xf7, 1)
    vrMasterClockM = (0xf8, 2)
    vrLedLevelRED = (0xfa, 1)
    vrLedLevelGRN = (0xfb, 1)
    vrLedLevelYEL = (0xfc, 1)
    vcBaudHost = (0xfe, 2)


class DumpMode(enum.Enum):
    Raw = 0
    Burst = 1
    Summed = 2
    MinMax = 3
    AndOr = 4
    Native = 5
    Filter = 6
    Span = 7


class TraceMode(enum.Enum):
    Analog = 0
    AnalogFast = 4
    AnalogShot = 11
    Mixed = 1
    MixedFast = 5
    MixedShot = 12
    Logic = 14
    LogicFast = 15
    LogicShot  = 13
    AnalogChop = 2
    AnalogFastChop = 6
    AnalogShotChop = 16
    MixedChop = 3
    MixedFastChop = 7
    MixedShotChop = 17
    Macro = 18
    MacroChop = 19


class BufferMode(enum.Enum):
    Single = 0
    Chop = 1
    Dual = 2
    ChopDual = 3
    Macro = 4
    MacroChop = 5


class ClockMode(enum.Enum):
    Mixed = 0
    MixedFast = 1
    MixedShot = 2
    Logic = 3
    LogicFast = 4
    LogicShot = 5
    Chop = 6
    ChopFast = 7
    ChopShot = 8
    Macro = 9


class StreamMode(enum.Enum):
    StreamAny = 0
    StreamAll = 1
    StreamRaw = 2
    StreamOne = 4
    StreamTwo = 3


class GeneratorMode(enum.Enum):
    Stop = 1
    Play = 2
    Clock = 3


class BitScope(asyncio.Protocol):

    def __init__(self, loop=None):
        super().__init__()
        if loop is None:
            loop = asyncio.get_event_loop()

        self._loop = loop
        self.transport = None

        self._buffer = b''
        self._queue = deque()
        self._callbacks = []

    def add_data_callback(self, cb):
        self._callbacks.append(cb)

    def remove_data_callback(self, cb):
        self._callbacks.remove(cb)

    def __await__(self):
        if self.transport is None:
            yield

    def connection_made(self, transport: SerialTransport):
        self.transport = transport
        self.guarded_write(b'!')

    def data_received(self, data):
        if not self._queue:
            for cb in self._callbacks:
                cb(data)
            return

        self._buffer += data

        while self._queue and self._buffer.startswith(self._queue[0][0]):
            bytes, fut = self._queue.popleft()
            self._buffer = self._buffer[len(bytes):]
            fut.set_result(None)

    def connection_lost(self, exc):
        for (bytes, fut) in self._queue:
            fut.cancel()

        self._queue.clear()
        self._buffer = b''

    async def triggeredCapture(self):
        await self.guarded_write(b">")
        await self.guarded_write(b"U")
        await self.guarded_write(b"D")

    async def streamingCapture(self):
        await self.guarded_write(b">")
        await self.guarded_write(b"U")
        await self.guarded_write(b"T")

    async def reset(self):
        fut = self.guarded_write(b'!')
        await asyncio.sleep(0.1)
        if not self._buffer.endswith(b'!'):
            raise RuntimeError("Bitscope failed to reset!")
        self._buffer = b''
        fut.set_result(None)
        self._queue.clear()

    def guarded_write(self, toWrite):
        fut = self._loop.create_future()
        self._queue.append((toWrite, fut))
        self.transport.write(toWrite)
        return fut

    def write_reg(self, reg, val):
        if isinstance(val, enum.Enum):
            val = val.value

        regAddr, nBytes = reg

        hexReg = binascii.hexlify(struct.pack('<B', regAddr))
        hexVal = binascii.hexlify(struct.pack('<I', val))

        toWrite = (  b'[' + hexReg + b']@'
                   + b'sn'.join([ b'[' + hexVal[i:i+2] + b']'
                                  for i in range(0, nBytes * 2, 2) ])
                   + b's')

        return self.guarded_write(toWrite)

