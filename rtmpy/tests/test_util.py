# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.util}
"""

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy import util

class UptimeTestCase(unittest.TestCase):
    def test_uptime(self):
        util.uptime()

import sys

if sys.platform.startswith('darwin'):
    UptimeTestCase.test_uptime.todo = unittest.makeTodo((NotImplementedError, ''))
