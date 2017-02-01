# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2015 - 2017 Arno Rehn <arno@arnorehn.de>

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


from common import DataSink
from common.traits import Path as PathTrait
from enum import Enum, unique
from traitlets import Bool, Enum as EnumTrait, Unicode
import numpy as np
from datetime import datetime
import logging
from copy import deepcopy


def _getManipulatorValueInPreferredUnits(m):
    val = m.value

    pref_units = m.trait_metadata('value', 'preferred_units')
    if pref_units:
        val = val.to(pref_units)

    return val


class DataSaver(DataSink):

    @unique
    class Formats(Enum):
        Text = 0
        HDF5 = 1
        Numpy = 2

    extension = {Formats.Text: '.txt', Formats.HDF5: '.hdf5',
                 Formats.Numpy: '.npz'}

    path = PathTrait(is_file=False, must_exist=True).tag(name="Path")
    fileFormat = EnumTrait(Formats, Formats.Text).tag(name="File format")
    textFileWithHeaders = Bool(False).tag(name="Write header to text files")
    fileNameTemplate = Unicode('{date}-{name}',
                               help="File name template, valid identifiers "
                                    "are:\n"
                                    "{name}: The main file name\n"
                                    "{date}: The current date and time").tag(
                               name="File name template")
    mainFileName = Unicode('data').tag(name="Main file name")

    enabled = Bool(True, help="Whether data storage is enabled").tag(
                         name="Enabled")

    _manipulators = {}
    _attributes = {}

    # from https://msdn.microsoft.com/en-us/library/aa365247
    _forbiddenCharacters = r'"*/:<>?\|'
    _fileNameTranslationTable = str.maketrans(_forbiddenCharacters,
                                              '_' * len(_forbiddenCharacters))

    def registerManipulator(self, manipulator, name=None):
        if name is None:
            name = manipulator.objectName

        self._manipulators[name] = manipulator

        trait = deepcopy(self.traits()['fileNameTemplate'])
        additionalHelpString = ('\n{{{}}}: The value of manipulator {}'
                                .format(name, manipulator.objectName))
        trait.help += additionalHelpString
        if 'help' in trait.metadata:
            trait.metadata['help'] += additionalHelpString
        self.add_traits(fileNameTemplate=trait)

    def registerObjectAttribute(self, inst, attr, name=None):
        if name is None:
            name = attr

        self._attributes[name] = (inst, attr)

        trait = deepcopy(self.traits()['fileNameTemplate'])
        additionalHelpString = ('\n{{{}}}: The value of "{}.{}"'
                                .format(name, str(inst), attr))
        trait.help += additionalHelpString
        if 'help' in trait.metadata:
            trait.metadata['help'] += additionalHelpString
        self.add_traits(fileNameTemplate=trait)


    def _getFileName(self):
        date = datetime.now().isoformat().replace(':', '-')

        manipValues = {k: '{:.3fC~}'
                       .format(_getManipulatorValueInPreferredUnits(m))
                       for k, m in self._manipulators.items()}

        attributeValues = {k: str(getattr(inst, name))
                           for k, (inst, name) in self._attributes.items()}

        formattedName = self.fileNameTemplate.format(date=date,
                                                     name=self.mainFileName,
                                                     **manipValues,
                                                     **attributeValues)
        formattedName += self.extension[self.fileFormat]
        formattedName = formattedName.translate(self._fileNameTranslationTable)
        return str(self.path.joinpath(formattedName))

    def _saveTxt(self, data):
        if len(data.axes) > 1 or len(data.axes) == 0:
            raise Exception("Only 1-dimensional data can be saved as text "
                            "files!")

        toSave = np.array([data.axes[0].magnitude, data.data.magnitude]).T
        header = ''
        if self.textFileWithHeaders:
            header = '{:C} {:C}'.format(data.axes[0].units, data.data.units)
        filename = self._getFileName()
        np.savetxt(filename, toSave, header=header)
        return filename

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
        return fileName

    def process(self, data):
        if not self.enabled:
            logging.info("Data storage is disabled, not saving data.")
            return

        filename = None
        if self.fileFormat == self.Formats.Text:
            filename = self._saveTxt(data)
        elif self.fileFormat == self.Formats.HDF5:
            filename = self._saveHDF5(data)
        elif self.fileFormat == self.Formats.Numpy:
            filename = self._saveNumpy(data)

        logging.info("Saved data as {}".format(filename))
