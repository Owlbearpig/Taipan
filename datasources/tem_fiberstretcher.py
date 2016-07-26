# -*- coding: utf-8 -*-
"""
Created on Wed Jul 20 16:07:15 2016

@author: Arno Rehn
"""

import asyncio
from common import DataSet, DataSource, Q_, action
from asyncioext import ensure_weakly_binding_future
from threading import Lock
import re
from serial import Serial, aio as aioserial
from serial.threaded import Packetizer, LineReader
import logging
from traitlets import Bool, Int, observe
from multiprocessing import Process, Queue
import struct
import binascii
import numpy as np
import time
from common.traits import DataSet as DataSetTrait
import traceback

_replyExpression = re.compile(r'([a-zA-Z0-9]+)=\s*([0-9]+)')


class PulseReader(Packetizer):

    TERMINATOR = b'\r'

    pulse = b''

    def __init__(self, q):
        super().__init__()
        self.q = q

    def handle_packet(self, packet):
        self.pulse += packet
        if self.pulse.endswith(b'X') or self.pulse.endswith(b'Y'):
            self.handle_hex_pulse(self.pulse[:-1])
            self.pulse = b''

    def handle_hex_pulse(self, hexPulse):
        rawPulse = binascii.a2b_hex(hexPulse)
        pulse = struct.unpack('>{}h'.format(int(len(rawPulse) / 2)), rawPulse)
        pulse = np.array(pulse, dtype=float)
        pulse -= np.mean(pulse)
        print("putting pulse with length {}".format(len(pulse)))
        self.q.put(pulse)


def read_pulse_data(port, q):
    loop = asyncio.new_event_loop()

    coro = aioserial.create_serial_connection(loop, lambda: PulseReader(q),
                                              port, baudrate=115200)

    loop.run_until_complete(coro)
    loop.run_forever()


class TEMFiberStretcher(DataSource):

    _lineReader = None

    handlers = []

    _blockObserver = False

    recPoints = Int(0, read_only=True)
    recStart = Int(0)
    recStop = Int(0)
    recInterval = Int(0)
    average = Int(0)
    mScanEnable = Bool(False)
    scanEnable = Bool(False)
    measurement = Bool(False)
    risingOnly = Bool(True)

    scanRecStart = Int(0)

    dcValue = Int(0)
    dcOut = Bool(False)

    currentData = DataSetTrait(read_only=True).tag(name="Live data",
                                                   data_label="Amplitude",
                                                   axes_labels=["Time"])

    def __init__(self, controlPort, dataPort, objectName=None, loop=None):
        super().__init__(objectName, loop)

        self.controlPort = controlPort
        self.dataPort = dataPort
        self.commLock = Lock()

        self.handlers.append(self.update_handler)

    @observe('recPoints', 'recStart', 'recStop', 'average', 'mScanEnable',
             'scanEnable', 'measurement', 'risingOnly', 'recInterval', 'dcOut',
             'dcValue', 'scanRecStart')
    def observer(self, change):
        logging.info("TEMFS: Trait change '{x[name]}' = {x[new]}"
                     .format(x=change))
        if self._blockObserver:
            return

        self.setVar(change['name'], change['new'])

    @classmethod
    def _sanitizeCommand(cls, cmd):
        cmd = cmd.lower()
        return cmd

    async def query(self, var):
        self.send(var + '=')
        reply = await self.expect_single(r'^{}=\s*([0-9]+)'.format(var),
                                         re.IGNORECASE)
        val = int(reply.groups()[0])
        return val

    def update_handler(self, line):
        match = _replyExpression.match(line)
        if not match:
            return

        var = match.groups()[0]
        val = int(match.groups()[1])

        possibleTraits = [trait for name, trait in self.traits().items()
                          if name.lower() == var.lower()]
        if not possibleTraits:
            logging.info("TEMFiberStretcher: Got update for variable {}={} "
                         "but no trait with a matching name."
                         .format(var, val))
            return

        trait = possibleTraits[0]
        self._blockObserver = True
        try:
            traitType = type(trait.get(self))
            trait.set(self, traitType(val))
        finally:
            self._blockObserver = False

    def expect_single(self, expect, flags=0):
        fut = asyncio.Future(loop=self._loop)

        def predicate(x):
            match = re.match(expect, x, flags=flags)
            if match:
                fut.set_result(match)
                self.handlers.remove(predicate)

        self.handlers.append(predicate)
        return fut

    def setVar(self, var, value):
        value = int(value)
        self.send('{}={}'.format(var, value))

    def send(self, command):
        command = self._sanitizeCommand(command)
        logging.info("TEMFS:SEND: {}".format(command))
        self._lineReader.write_line(command)

    def handle_line(self, line):
        logging.info("TEMFS:HANDLING {}".format(line))

        for x in self.handlers:
            x(line)

    def handle_error(self, error):
        print(error)

    _dt = 4.36968965E-15 * 1e12

    async def readPulseFromQueue(self):
        try:
            while True:
                # yield control to the event loop once
                await asyncio.sleep(0)

                while not self._pulseQueue.empty():
                    pulse = self._pulseQueue.get()
                    pulse = Q_(pulse)

                    axis = (self.recStart + np.arange(len(pulse)) *
                            self.recInterval) * self._dt
                    axis = Q_(axis, 'ps')

                    data = DataSet(pulse, [axis])

                    self.set_trait('currentData', data)
        except:
            traceback.print_exc()

    @action("Reset counter")
    def resetCounter(self):
        self.send("ResetCounter")

    async def __aenter__(self):
        await super().__aenter__()

        self._controlTransport, self._lineReader = \
            await aioserial.create_serial_connection(self._loop, LineReader,
                                                     self.controlPort,
                                                     baudrate=57600)
        self._lineReader.handle_line = self.handle_line
        await asyncio.sleep(0)

        self.send('measurement=')
        self.send('mscanenable=')
        self.send('scanenable=')
        self.send('recpoints=')
        self.send('recinterval=')
        self.send('recstart=')
        self.send('recstop=')
        self.send('average=')
        self.send('risingonly=')
        self.send('dcvalue=')
        self.send('dcout=')

        self.measurement = False
        self.mScanEnable = False
        self.scanEnable = False

        self._pulseQueue = Queue()
        self._pulseReader = Process(target=read_pulse_data,
                                    args=(self.dataPort, self._pulseQueue))
        self._pulseReader.start()
        self.pulseReaderCoro = ensure_weakly_binding_future(self.readPulseFromQueue)

        return self

    async def __aexit__(self, *args):
        self.measurement = False
        self.mScanEnable = False
        self.scanEnable = False
        self.pulseReaderCoro.cancel()
        time.sleep(1)
        self._pulseReader.terminate()
        await super().__aexit__(*args)

if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)

    loop = asyncio.get_event_loop()
    print(id(loop))

    async def run():
        async with TEMFiberStretcher('/tmp/fiberstretcher0', '/tmp/fiberstretcher1', loop=loop) as fs:
            fs.dcValue = 8000
            fs.recStart = 1000
            fs.recStop = 10000
            fs.recInterval = 30
            await asyncio.sleep(2)
            fs.risingOnly = False
            fs.measurement = True
            fs.mScanEnable = True
            await asyncio.sleep(5)
            fs.measurement = False
            await asyncio.sleep(2)

    loop.run_until_complete(run())


#    print(fs.send('hello'))
#    print(fs.query('RecInterval'))

#    reply = 'RecInterval asd= 20'
#    match = _replyExpression.match(reply)
#    assert match, 'failed'
#