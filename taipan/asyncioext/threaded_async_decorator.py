# -*- coding: utf-8 -*-
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

import asyncio
from functools import partial


def threaded_async(func=None, loop=None, executor=None):
    r""" Transforms a normal function into an ``async`` one that runs in a
    thread (or, more specifically, in ``executor``).

    Parameters
    ----------

    loop : BaseEventLoop, optional
        The event loop in which the function is run.
        Default: ``asyncio.get_event_loop()``.

    executor : Executor, optional
        The `Executor` instance in which the function in run.
        Default: ``None``, resulting in the default executor of ``loop``.
    """

    # if ``func`` is None, return a partially bound function as the 'real'
    # decorator
    if func is None:
        return partial(threaded_async, loop=loop, executor=executor)

    async def async_executor_wrapper(*args, **kwargs):
        theloop = loop
        if theloop is None:
            theloop = asyncio.get_event_loop()
        return await theloop.run_in_executor(executor,
                                             partial(func, *args, **kwargs))

    return async_executor_wrapper

if __name__ == '__main__':
    help(threaded_async)