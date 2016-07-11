# -*- coding: utf-8 -*-
"""
Created on Mon Jul 11 12:26:34 2016

@author: Arno Rehn
"""


from common import DataSink
from common.traits import Path as PathTrait
from enum import Enum, unique
from traitlets import Bool, Enum as EnumTrait, Unicode
import numpy as np
from datetime import datetime


class DataSaver(DataSink):

    @unique
    class Formats(Enum):
        Text = 0
        HDF5 = 1
        Numpy = 2

    extension = {Formats.Text: '.txt', Formats.HDF5: '.hdf5',
                 Formats.Numpy: '.npz'}

    path = PathTrait().tag(name="Path")
    fileFormat = EnumTrait(Formats, Formats.Text).tag(name="File format")
    textFileWithHeaders = Bool(False).tag(name="Write header to text files")
    fileNameTemplate = Unicode('{date}-{name}')
    mainFileName = Unicode('data')

    def _getFileName(self):
        date = datetime.now().isoformat().replace(':', '-')
        formattedName = self.fileNameTemplate.format(date=date,
                                                     name=self.mainFileName)
        formattedName += self.extension[self.fileFormat]
        return formattedName

    def _saveTxt(self, data):
        if len(data.axes) > 1 or len(data.axes) == 0:
            raise Exception("Only 1-dimensional data can be saved as text "
                            "files!")

        toSave = np.array([data.axes[0].magnitude, data.data.magnitude]).T
        header = ''
        if self.textFileWithHeaders:
            header = '{:C} {:C}'.format(data.axes[0].units, data.data.units)
        np.savetxt(self._getFileName(), toSave, header=header)

    def _saveHDF5(self, data):
        raise NotImplementedError("Saving as HDF5 has not yet been "
                                  "implemented")

    def _saveNumpy(self, data):
        fileName = self._getFileName()
        axesUnits = ['{:C}'.format(ax.units) for ax in data.axes]
        dataUnits = '{:C}'.format(data.data.units)
        unitlessAxes = [ax.magnitude for ax in data.axes]
        np.savez_compressed(fileName, axes=unitlessAxes, axesUnits=axesUnits,
                            data=data.data.magnitude, dataUnits=dataUnits)

    def process(self, data):
        if self.fileFormat == self.Formats.Text:
            self._saveTxt(data)
        elif self.fileFormat == self.Formats.HDF5:
            self._saveHDF5(data)
        elif self.fileFormat == self.Formats.Numpy:
            self._saveNumpy(data)
