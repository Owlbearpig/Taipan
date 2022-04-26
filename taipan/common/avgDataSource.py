# -*- coding: utf-8 -*-
"""
Created on Thu Sep  8 12:21:50 2016

@author: dave
"""
import asyncio

import traitlets

import taipan.common.components
from taipan.common import DataSource, action
from traitlets import Integer, Instance
import logging


class AverageDataSource(DataSource):
    """
    Collects, sums up datasets and divides by the number of datasets.

    Attributes
    ----------
    numberofAverages : `traitlets.Integer`
        Total number of datasets to collect. Set by the user.
    currentAverages : `traitlets.Integer`
        Dataset counter. Read only.
    dataLen : `traitlets.Integer`
        Number of datapoints in a dataset. Read only.
    singleSource: `traitlets.Instance`
        traitlets.Instance, Instance of class components.DataSource
    dataSource: `taipan.common.components.DataSource`
        class components.DataSource instance of data acquisition device class.
    objectName: `str`, optional
        UI element name.
    loop: `asyncio.BaseEventLoop`, optional
        Async loop from qasync.QEventLoop initialized in load_with_ui.py

    Methods
    -------
    async start()
        Awaits singleSource.start()
    async stop()
        Awaits singleSource.stop().
    async readDataLength()
        Calls singleSource.readDataSet() and sets its len in dataLen trait.
        Implemented as @action.
    async readDataSet()
        Performs dataLen checks, sums up singleSource.readDataSet()
        and divides by count.
    """

    numberofAverages = Integer(1, read_only=False).tag(
        name='Number of Averages')

    currentAverages = Integer(0, read_only=True).tag(
        name='current Averages')

    dataLen = Integer(0, read_only=True).tag(
        name="Expected Data Length")

    singleSource = Instance(DataSource, allow_none=True)

    def __init__(self, dataSource, objectName=None, loop=None):
        """
        Parameters
        ----------
        dataSource: `taipan.common.components.DataSource`
            class components.DataSource instance of data acquisition device class.
        objectName: `str`, optional
            UI element name.
        loop: `asyncio.BaseEventLoop`, optional
            Async loop from asyncio.BaseEventLoop initialized in load_with_ui.py
        """

        super().__init__(objectName, loop)
        self.singleSource = dataSource

    async def start(self):
        """Awaits self.singleSource.start()"""
        await self.singleSource.start()

    async def stop(self):
        """Awaits self.singleSource.stop() and sets trait currentAverages to 1"""
        self.set_trait('currentAverages', 1)
        await self.singleSource.stop()

    @action("expected length")
    async def readDataLength(self):
        """
        Calls singleSource.readDataSet() and sets its len in dataLen trait.
        Implemented as @action.
        """
        cd = await self.singleSource.readDataSet()
        self.set_trait('dataLen', len(cd.data))

    async def readDataSet(self):
        """
        Reads dataset from singleSource, does the averaging and sets traits.

        Returns
        -------
        `taipan.common.dataset.DataSet`
            Dataset containing averaged data. Has axes of first dataset from singleSource.readDataSet().
        """

        if self.dataLen == 0:
            logging.info("Please set the expected data length!, try to guess it")
            await self.readDataLength()

        if self.numberofAverages < 1:
            logging.info("Averaging: Please insert a positive number, averages set to 1")
            self.numberofAverages = 1
        avDataSet = await self.singleSource.readDataSet()
        while len(avDataSet.data) != self.dataLen:
            logging.info("Failed to read data with correct length, retry!")
            avDataSet = await self.singleSource.readDataSet()

        self.set_trait('currentAverages', 1)
        while self.currentAverages < self.numberofAverages:
            singleSet = await self.singleSource.readDataSet()
            while len(singleSet.data) != self.dataLen:
                logging.info("Failed to read data with correct length, retry!")
                singleSet = await self.singleSource.readDataSet()

            avDataSet.data += singleSet.data
            self.set_trait('currentAverages', self.currentAverages + 1)
        avDataSet.data /= self.numberofAverages
        self._dataSetReady(avDataSet)
        return avDataSet
