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

from common import DataSet, DataSource, Q_
from serial import Serial
from asyncioext import ensure_weakly_binding_future, threaded_async
import asyncio
import numpy as np
import logging
from common.traits import Quantity


class NuveClimateCabinet(DataSource):

    temperature = Quantity(Q_(0, 'degC'), read_only=True).tag(
                                          name="Temperature")
    humidity = Quantity(Q_(0), read_only=True).tag(
                               name="Relative humditiy")

    def __init__(self, port=None, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self.port = port

        class TempDataSource(DataSource):
            async def readDataSet(myself):
                return DataSet(np.array(self.temperature))

        class HumidityDataSource(DataSource):
            async def readDataSet(myself):
                return DataSet(np.array(self.humidity))

        self.temperatureDataSource = TempDataSource(loop=loop)
        self.humidityDataSource = HumidityDataSource(loop=loop)

    async def __aenter__(self):
        await super().__aenter__()
        self._continuous_update_fut = \
            ensure_weakly_binding_future(self._continuous_update)
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._continuous_update_fut.cancel()

    async def _continuous_update(self):
        while True:
            try:
                await self._update_values()
            except Exception as e:
                logging.warning("Failed to update climate cabinet values: {}"
                                .format(e))
            await asyncio.sleep(1)

    @threaded_async
    def _update_values(self):
        def cmd_read_array(offset, address):
            buffer = bytearray(12)

            buffer[0] = 0x13
            buffer[1] = b'R'[0]
            buffer[2] = b'A'[0]
            buffer[3] = offset // 10
            buffer[4] = offset % 10
            buffer[5] = address // 100
            buffer[6] = (address % 100) // 10
            buffer[7] = address % 10

            checksum = 0
            for i in range(3, 8):
                checksum += buffer[i]

            buffer[8] = checksum // 100
            buffer[9] = (checksum % 100) // 10
            buffer[10] = checksum % 10
            buffer[11] = 0x10

            return buffer

        def process_read_array_reply(reply):
            offset = reply[1] * 10 + reply[2]
            if reply[3 + 3 * offset + 3] != 0x10:
                raise RuntimeError("Malformed reply!")

            checksum = 0
            for i in range(0, 2 + 3 * offset):
                checksum += reply[i + 1]

            if checksum != (  reply[3 + 3 * offset] * 100
                            + reply[4 + 3 * offset] * 10
                            + reply[5 + 3 * offset]):
                raise RuntimeError("Checksum failure!")

            array = bytearray(offset)
            for i in range(offset):
                array[i] = (  reply[3 + 3 * i] * 100
                            + reply[4 + 3 * i] * 10
                            + reply[5 + 3 * i])
            return array

        def get_temp_humidity_time(values):
            temperature = (values[0] * 256 + values[1]) / 10
            humidity = values[2]
            time = values[3] * 256 + values[4]

            return Q_(temperature, 'degC'), Q_(humidity / 100)

        ser = Serial(self.port, 9600)

        ser.write(cmd_read_array(5, 100))
        reply = ser.read(22)
        values = process_read_array_reply(reply)

        temp, hum = get_temp_humidity_time(values)
        self.set_trait('temperature', temp)
        self.set_trait('humidity', hum)

        self.temperatureDataSource._dataSetReady(
            DataSet(np.array(self.temperature)))
        self.humidityDataSource._dataSetReady(
            DataSet(np.array(self.humidity)))

_debugNuvePort = '/tmp/climate_cabinet'

if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    async def run():
        async with NuveClimateCabinet(_debugNuvePort) as ncc:
            await asyncio.sleep(5)

    loop.run_until_complete(run())

elif __name__ == '__guimain__':
    class AppRoot(NuveClimateCabinet):
        def __init__(self, *args):
            super().__init__(*args)
            self.objectName = "Nuve Climate Cabinet"

        async def __aenter__(self):
            self.port = _debugNuvePort
            return await super().__aenter__()
