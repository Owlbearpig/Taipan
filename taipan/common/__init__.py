"""
This file is part of Taipan.

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

from .components import (action, ComponentBase, DataSource,
                         DAQDevice, DataSink, Manipulator, PostProcessor)
from .dataset import DataSet
from .scan import Scan, MultiDataSourceScan
from .table import TabularMeasurements
from .table_2m import TabularMeasurements2M
from .table_3m import TabularMeasurements3M
from .units import ureg, Q_
from .multiDataSource import MultiDataSource
from .traits import Quantity

class TimeoutException(Exception):
    pass
