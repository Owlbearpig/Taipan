Taipan
======

Taipan, the Terahertz Acquisition and Imaging Program for ANything

Overview
--------
Taipan is a modular framework intended for data acquisition and measurements.
Its internal structure follows the
[Naked Objects pattern](https://en.wikipedia.org/wiki/Naked_objects): The
classes in the main application are only concerned with business logic. The
user interface is then automatically generated from metadata associated with
the measurement objects.

Internal Structure
------------------
*ComponentBase*: All classes that are part of the measurement scheme should
derive from this. It provides common methods and attributes for working with
metadata and configuration settings.

*DataSource*: Anything that provides data should derive from this class.

*DAQDevice*: Sub-class of DataSource, provides additional attributes for
concrete data acquisition devices.

*DataSink*: Anything that accepts data and does something with it.

*PostProcessor*: An amalgamation of DataSource and DataSink. A PostProcessor
accepts data, transforms it and provides access to the results.

*Manipulator*: Anything that can change a parameter of the measurement setup,
for example a translation stage.

*DataSet*: Objects of this type represent multi-dimensional data and the
accompanying axes. For example, a THz TDS image will be represented by a
three dimensional data array and three axis vectors. The dimensions will be
time, position x, position y (not necessarily in that order). DataSet provides
methods to check the consistency of the stored data, i.e. that the number of
axes and number of elements per axis vector match the shape of the data array.

*Scan*: A higher-level class implementing a sweep of one parameter. It thus
needs references to a Manipulator and a DataSource. The Scan class supports
both continuous scans (i.e. the Manipulator moves continuously and the
DataSource records continouosly) as well as stepped scans (i.e. the Manipulator
is moved step by step and the DataSources acquires is single point at every
step).
Any Scan object is a DataSource itself. Multidimensional parameter sweeps can
thus be implemented by cascading many Scan objects, where one Scan is the
other's DataSource.

Dependencies
------------
* Python 3.5+
* jsonrpclib-pelix
* pyserial
* pyvisa
* pyvisa-py

Coding style
------------
Try to adhere to [PEP-8](https://www.python.org/dev/peps/pep-0008) for the most
part. Important points:
* 4 spaces indent
* 79 chars line width
* Contrary to PEP-8, use camelCase for functions and variables