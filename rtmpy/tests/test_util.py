# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.util}
"""

import __builtin__
import sys, time, warnings

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy import util

class BufferedByteStreamTestCase(unittest.TestCase):
    def setUp(self):
        self.stream = util.BufferedByteStream()

    def _write(self, bytes):
        pos = self.stream.tell()
        self.stream.write(bytes)
        self.stream.seek(pos)

    def test_consume(self):
        self.stream.write('abcdefg')
        self.stream.seek(2)
        self.stream.consume()
        self.assertEquals(self.stream.getvalue(), 'cdefg')
        self.assertEquals(self.stream.tell(), 5)

        self.stream.seek(2)
        self.stream.consume()
        self.assertEquals(self.stream.getvalue(), 'efg')
        self.assertEquals(self.stream.tell(), 3)

        self.stream.seek(0, 2)
        self.stream.consume()
        self.assertEquals(self.stream.getvalue(), '')
        self.assertEquals(self.stream.tell(), 0)

    def test_read3byte_uint(self):
        self._write('\xff\xff\xff')
        self.assertEquals(self.stream.read_3byte_uint(), 0xffffff)

        self._write('\x00\x00\x00')
        self.assertEquals(self.stream.read_3byte_uint(), 0)

        self._write('\x00\x00')
        self.assertRaises(EOFError, self.stream.read_3byte_uint)

    def test_write3byte_uint(self):
        self.stream.write_3byte_uint(0)
        self.assertEquals(self.stream.getvalue(), '\x00\x00\x00')
        self.stream.truncate()

        self.stream.write_3byte_uint(16777215)
        self.assertEquals(self.stream.getvalue(), '\xff\xff\xff')
        self.stream.truncate()

        self.assertRaises(ValueError, self.stream.write_3byte_uint, 16777216)
        self.assertRaises(ValueError, self.stream.write_3byte_uint, -1)


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
    def test_okay(self):
        self.assertNotEquals(util.uptime_win32(), 0)


class DarwinUptimeTestCase(UptimeTestCase):
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
