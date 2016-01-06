# -*- coding: utf-8 -*-
"""
Created on Tue Oct 20 10:36:07 2015

@author: Arno Rehn
"""

import asyncio
import weakref


def ensure_weakly_binding_future(method):
    class Canceller:
        def __call__(self, proxy):
            self.future.cancel()

    canceller = Canceller()
    proxy_object = weakref.proxy(method.__self__, canceller)
    weakly_bound_method = method.__func__.__get__(proxy_object)
    future = asyncio.ensure_future(weakly_bound_method())
    canceller.future = future
