# -*- coding: utf-8 -*-
"""
Created on Wed Oct 28 13:55:46 2015

@author: Arno Rehn
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
