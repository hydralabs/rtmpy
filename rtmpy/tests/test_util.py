# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
Tests for L{rtmpy.util}
"""

import __builtin__
import sys
import warnings

from twisted.trial import unittest

from rtmpy import util


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


class ParamedStringTestCase(unittest.TestCase):
    """
    Tests for L{util.ParamedString}
    """

    def test_create(self):
        """
        Simple creation.
        """
        x = util.ParamedString('foobar')

        self.assertEqual(x, 'foobar')

    def test_params(self):
        """
        """
        x = util.ParamedString('foobar?foo=foo&bar=bar&bar=baz')

        self.assertEqual(x, 'foobar')
        self.assertEqual(x.foo, 'foo')
        self.assertEqual(x.bar, ['bar', 'baz'])

        self.assertRaises(AttributeError, getattr, x, 'baz')


if not sys.platform.startswith('linux'):
    LinuxUptimeTestCase.skip = 'Tested platform is not linux'

if not sys.platform.startswith('win32'):
    Win32UptimeTestCase.skip = 'Tested platform is not win32'

if not sys.platform.startswith('darwin'):
    DarwinUptimeTestCase.skip = 'Tested platform is not darwin'

UnknownPlatformUptimeTestCase = None
DarwinUptimeTestCase = None