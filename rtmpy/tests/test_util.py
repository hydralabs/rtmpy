# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.util}
"""

import __builtin__
import sys, time, warnings

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy import util

class BufferedByteStreamTestCase(unittest.TestCase):
    def test_consume(self):
        stream = util.BufferedByteStream()

        stream.write('abcdefg')
        stream.seek(2)
        stream.consume()
        self.assertEquals(stream.getvalue(), 'cdefg')
        self.assertEquals(stream.tell(), 5)

        stream.seek(2)
        stream.consume()
        self.assertEquals(stream.getvalue(), 'efg')
        self.assertEquals(stream.tell(), 3)

        stream.seek(0, 2)
        stream.consume()
        self.assertEquals(stream.getvalue(), '')
        self.assertEquals(stream.tell(), 0)


class UptimeTestCase(unittest.TestCase):
    def setUp(self):
        util.boottime = None

class LinuxUptimeTestCase(UptimeTestCase):
    def setUp(self):
        UptimeTestCase.setUp(self)

        self.orig_open = __builtin__.open

    def tearDown(self):
        __builtin__.open = self.orig_open

    def test_error_open(self):
        def open_error(path, mode=None):
            raise IOError

        __builtin__.open = open_error
        self.assertEquals(util.uptime_linux(), 0)

    def test_bad_content(self):
        def open_error(path, mode=None):
            class BadContentFileObject:
                read = lambda _: '123.bar'
                close = lambda _: None
                readlines = lambda _: []

            return BadContentFileObject()

        __builtin__.open = open_error

        self.assertEquals(util.uptime_linux(), 0)

    def test_okay(self):
        self.assertNotEquals(util.uptime_linux(), 0)


class Win32UptimeTestCase(UptimeTestCase):
    def setUp(self):
        UptimeTestCase.setUp(self)

        self.orig_open = __builtin__.open

    def tearDown(self):
        __builtin__.open = self.orig_open

    def test_error_open(self):
        def open_error(path, mode=None):
            raise IOError

        __builtin__.open = open_error
        self.assertEquals(util.uptime_win32(), 0)

    def test_bad_content(self):
        def open_error(path, mode=None):
            class BadContentFileObject:
                read = lambda _: '123.bar'
                close = lambda _: None
                readlines = lambda _: []

            return BadContentFileObject()

        __builtin__.open = open_error

        self.assertEquals(util.uptime_win32(), 0)

    def test_okay(self):
        self.assertNotEquals(util.uptime_win32(), 0)


class DarwinUptimeTestCase(UptimeTestCase):
    def setUp(self):
        UptimeTestCase.setUp(self)

        self.orig_func = util._find_command

    def tearDown(self):
        util._find_command = self.orig_func

    def test_okay(self):
        self.assertNotEquals(util.uptime_darwin(), 0)


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


if not sys.platform.startswith('linux'):
    LinuxUptimeTestCase.skip = 'Tested platform is not linux'

if not sys.platform.startswith('win32'):
    Win32UptimeTestCase.skip = 'Tested platform is not win32'

if not sys.platform.startswith('darwin'):
    DarwinUptimeTestCase.skip = 'Tested platform is not darwin'
