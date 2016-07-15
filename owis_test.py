# -*- coding: utf-8 -*-
"""
Created on Fri Jul 15 14:26:21 2016

@author: Arno Rehn
"""

from common import ComponentBase, Manipulator, Q_
from stages.owis import Connection, AxisAtController
from traitlets import Instance


class AppRoot(ComponentBase):

    axis = Instance(Manipulator)

    def __init__(self, loop=None):
        super().__init__(objectName="Root",loop=loop)
        self.title = "Owis Test App"

        self.conn = Connection('/tmp/owis')
        self.axis = AxisAtController(self.conn, axis=3, pitch=Q_(200, 'count/mm'))

    async def __aenter__(self):
        await self.conn.__aenter__()
        await self.axis.__aenter__()
        return self
