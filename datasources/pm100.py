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

from common import Q_, DataSource, DataSet
from asyncioext import ensure_weakly_binding_future, threaded_async
import asyncio
import numpy as np
from common.traits import Quantity
from threading import Lock

class ThorlabsPM100(DataSource):

    power = Quantity(Q_(0, 'mW'), read_only=True).tag(name='Power')

    def __init__(self, resource=None, objectName=None, loop=None):
        super().__init__(objectName, loop)
        self._lock = Lock()
        self.resource = resource

    async def __aenter__(self):
        await super().__aenter__()
        self._continuousUpdateFut = \
            ensure_weakly_binding_future(self._continuousRead)
        return self

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        self._continuousUpdateFut.cancel()

    async def _continuousRead(self):
        while True:
            await self.readDataSet()
            await asyncio.sleep(0.1)

    @threaded_async
    def _guardedRead(self):
        with self._lock:
            return float(self.resource.ask('READ?'))

    async def readDataSet(self):
        val = await self._guardedRead()
        dset = DataSet(Q_(np.array(val), 'W'))
        self.set_trait('power', Q_(val, 'W'))
        self._dataSetReady(dset)


_debugThorlabsPM100Port = 'USB0::0x1313::0x8078::PM001874::INSTR'

if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    import visa
    rm = visa.ResourceManager()

    async def run():
        res = rm.open_resource(_debugThorlabsPM100Port)
        async with ThorlabsPM100(res) as pm100:
            await pm100.readDataSet()
            print("Current power: {}".format(pm100.power))

    loop.run_until_complete(run())

elif __name__ == '__guimain__':
    import visa
    rm = visa.ResourceManager()

    class AppRoot(ThorlabsPM100):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.objectName = "Thorlabs PM100D"
            self.resource = rm.open_resource(_debugThorlabsPM100Port)
