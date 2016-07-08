# -*- coding: utf-8 -*-
"""
Created on Thu Jul  7 09:17:32 2016

@author: Arno Rehn
"""

from datasources import TW4B


class AppRoot(TW4B):

    def __init__(self):
        super().__init__('192.168.134.16')
