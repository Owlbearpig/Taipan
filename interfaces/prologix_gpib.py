# -*- coding: utf-8 -*-
"""
This file is part of Taipan.

Copyright (C) 2015 Hernan E. Grecco <hernan.grecco@gmail.com>
Copyright (C) 2015 - 2016 Arno Rehn <arno@arnorehn.de>

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

from __future__ import division, unicode_literals, print_function, absolute_import
from threading import Lock
from bisect import bisect

from pyvisa import constants, logger

import importlib
_pyvisa_py_sessions = importlib.import_module('pyvisa-py.sessions')
Session = _pyvisa_py_sessions.Session
UnknownAttribute = _pyvisa_py_sessions.UnknownAttribute

gpib_prologix_device = None

def _find_listeners():
    """Find GPIB listeners.
    """
    setTimeout(20)
    gpib_prologix_device.write(b'++read_tmo_ms %d\n' % 15)
    for i in range(31):
        gpib_prologix_device.write(b'++spoll %d\n' % i)
        result = gpib_prologix_device.readline()
        if (result):
            yield i

StatusCode = constants.StatusCode
SUCCESS = StatusCode.success

_currentAddress = 0

def setTimeout(timeout):
    if gpib_prologix_device.timeout != timeout * 1e-3:
        gpib_prologix_device.timeout = timeout * 1e-3

def setAddress(address):
    global _currentAddress
    if _currentAddress != address:
        _currentAddress = address
        gpib_prologix_device.write(b'++addr %d\n' % address)

@Session.register(constants.InterfaceType.gpib, 'INSTR')
class GPIBSession(Session):
    """A GPIB Session that uses the Prologix-GPIB adapters to do the low level communication.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._termchar = None
        self._termchar_en = False
        self._timeout = 0.015
        self._pad = 0
        self._sad = 0
        self._lock = Lock()

    @staticmethod
    def list_resources():
        return ['GPIB0::%d::INSTR' % pad for pad in _find_listeners()]

    @classmethod
    def get_low_level_info(cls):
        gpib_prologix_device.write(b'++ver\n')
        ver = gpib_prologix_device.readline().strip().decode('ascii')
        return 'via %s' % ver

    def after_parsing(self):
        self._pad = self.parsed.primary_address

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value

    def close(self):
        pass

    def read(self, count):
        """Reads data from device or interface synchronously.

        Corresponds to viRead function of the VISA library.

        :param count: Number of bytes to be read.
        :return: data read, return value of the library call.
        :rtype: bytes, constants.StatusCode
        """

        with self._lock:
            setTimeout(self._timeout)
            setAddress(self._pad)

            gpib_prologix_device.write(b"++auto 1\n")

            try:
                # shortcut for reading without termination character
                if not self._termchar_en:
                    out = gpib_prologix_device.read(count)
                    status = constants.StatusCode.error_timeout if len(out) < count \
                             else constants.StatusCode.success_max_count_read
                    return out, status

                out = b''

                while True:
                    current = gpib_prologix_device.read(1)
                    if not current:
                        break

                    out += current
                    if self._termchar_en and self._termchar == current:
                        return (out,
                               constants.StatusCode.success_termination_character_read)
                    elif len(out) >= count:
                        return (out,
                               constants.StatusCode.success_max_count_read)

                return out, constants.StatusCode.error_timeout
            finally:
                gpib_prologix_device.write(b"++auto 0\n")

    def write(self, data):
        """Writes data to device or interface synchronously.

        Corresponds to viWrite function of the VISA library.

        :param data: data to be written.
        :type data: bytes
        :return: Number of bytes actually transferred, return value of the library call.
        :rtype: int, VISAStatus
        """

        with self._lock:
            setTimeout(self._timeout)
            setAddress(self._pad)

            logger.debug('Prologix-GPIB.write %r' % data)
            gpib_prologix_device.write(data)

            return SUCCESS

    def _get_attribute(self, attribute):
        """Get the value for a given VISA attribute for this session.

        Use to implement custom logic for attributes.

        :param attribute: Resource attribute for which the state query is made
        :return: The state of the queried attribute for a specified resource, return value of the library call.
        :rtype: (unicode | str | list | int, VISAStatus)
        """

        if attribute == constants.VI_ATTR_TERMCHAR:
            return ord(self._termchar), SUCCESS

        elif attribute == constants.VI_ATTR_TERMCHAR_EN:
            return type(constants.VI_TRUE)(self._termchar_en), SUCCESS

#        if attribute == constants.VI_ATTR_GPIB_READDR_EN:
#            # IbaREADDR 0x6
#            # Setting has no effect in linux-gpib.
#            return self.interface.ask(6), SUCCESS
#
        elif attribute == constants.VI_ATTR_GPIB_PRIMARY_ADDR:
            return self._pad, SUCCESS
#
#        elif attribute == constants.VI_ATTR_GPIB_SECONDARY_ADDR:
#            # IbaSAD 0x2
#            # Remove 0x60 because National Instruments.
#            sad = self.interface.ask(2)
#            if self.interface.ask(2):
#                return self.interface.ask(2) - 96, SUCCESS
#            else:
#                return constants.VI_NO_SEC_ADDR, SUCCESS
#
#        elif attribute == constants.VI_ATTR_GPIB_REN_STATE:
#            # I have no idea how to implement this.
#            raise NotImplementedError
#
#        elif attribute == constants.VI_ATTR_GPIB_UNADDR_EN:
#            # IbaUnAddr 0x1b
#            if self.interface.ask(27):
#                return constants.VI_TRUE, SUCCESS
#            else:
#                return constants.VI_FALSE, SUCCESS
#
#        elif attribute == constants.VI_ATTR_SEND_END_EN:
#            # IbaEndBitIsNormal 0x1a
#            if self.interface.ask(26):
#                return constants.VI_TRUE, SUCCESS
#            else:
#                return constants.VI_FALSE, SUCCESS
#
#        elif attribute == constants.VI_ATTR_INTF_NUM:
#            # IbaBNA 0x200
#            return self.interface.ask(512), SUCCESS
#
#        elif attribute == constants.VI_ATTR_INTF_TYPE:
#            return constants.InterfaceType.gpib, SUCCESS

        raise UnknownAttribute(attribute)

    def _set_attribute(self, attribute, attribute_state):
        """Sets the state of an attribute.

        Corresponds to viSetAttribute function of the VISA library.

        :param attribute: Attribute for which the state is to be modified. (Attributes.*)
        :param attribute_state: The state of the attribute to be set for the specified object.
        :return: return value of the library call.
        :rtype: VISAStatus
        """

        if attribute == constants.VI_ATTR_TERMCHAR:
            self._termchar = chr(attribute_state).encode('ascii')
            return SUCCESS

        elif attribute == constants.VI_ATTR_TERMCHAR_EN:
            self._termchar_en = bool(attribute_state)
            return SUCCESS

#        if attribute == constants.VI_ATTR_GPIB_READDR_EN:
#            # IbcREADDR 0x6
#            # Setting has no effect in linux-gpib.
#            if isinstance(attribute_state, int):
#                self.interface.config(6, attribute_state)
#                return SUCCESS
#            else:
#                return StatusCode.error_nonsupported_attribute_state
#
        elif attribute == constants.VI_ATTR_GPIB_PRIMARY_ADDR:
            # IbcPAD 0x1
            if isinstance(attribute_state, int) and 0 <= attribute_state <= 30:
                self._pad = attribute_state
                return SUCCESS
            else:
                return StatusCode.error_nonsupported_attribute_state
#
#        elif attribute == constants.VI_ATTR_GPIB_SECONDARY_ADDR:
#            # IbcSAD 0x2
#            # Add 0x60 because National Instruments.
#            if isinstance(attribute_state, int) and 0 <= attribute_state <= 30:
#                if self.interface.ask(2):
#                    self.interface.config(2, attribute_state + 96)
#                    return SUCCESS
#                else:
#                    return StatusCode.error_nonsupported_attribute
#            else:
#                return StatusCode.error_nonsupported_attribute_state
#
#        elif attribute == constants.VI_ATTR_GPIB_UNADDR_EN:
#            # IbcUnAddr 0x1b
#            try:
#                self.interface.config(27, attribute_state)
#                return SUCCESS
#            except gpib.GpibError:
#                return StatusCode.error_nonsupported_attribute_state
#
#        elif attribute == constants.VI_ATTR_SEND_END_EN:
#            # IbcEndBitIsNormal 0x1a
#            if isinstance(attribute_state, int):
#                self.interface.config(26, attribute_state)
#                return SUCCESS
#            else:
#                return StatusCode.error_nonsupported_attribute_state

        raise UnknownAttribute(attribute)
