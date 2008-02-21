# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.util}
"""

import sys, time, warnings

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy import util


class UptimeTestCase(unittest.TestCase):
    def test_uptime(self):
        util.uptime()
        util.boottime = None

    if sys.platform.startswith('linux'):
        def test_linux(self):
            now = time.time()
            ut = util.uptime_linux()

            self.assertTrue(type(ut), float)
            self.assertTrue(now > ut)

    elif sys.platform.startswith('win'):
        def test_win32(self):
            now = time.time()
            ut = util.uptime_win32()

            self.assertTrue(type(ut), float)
            self.assertTrue(now > ut)

    elif sys.platform.startswith('darwin'):
        def test_darwin(self):
            now = time.time()
            ut = util.uptime_darwin()

            self.assertTrue(type(ut), float)
            self.assertTrue(now > ut)


class UnknownPlatformUptimeTestCase(unittest.TestCase):
    def setUp(self):
        self.platform = sys.platform
        sys.platform = ''
        util.boottime = None

    def tearDown(self):
        sys.platform = self.platform

    def test_warning(self):
        warnings.filterwarnings('error', category=RuntimeWarning)
        self.assertRaises(RuntimeWarning, util.uptime)

        warnings.filterwarnings('ignore', category=RuntimeWarning)
        util.uptime()

        self.assertNotEquals(util.boottime, None)
