# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import defer, reactor

from rtmpy import rtmp
from rtmpy.rtmp import interfaces
from rtmpy.tests.rtmp import mocks


class HeaderTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.Header}
    """

    def test_interface(self):
        h = rtmp.Header()

        self.assertTrue(interfaces.IHeader.providedBy(h))

    def test_init(self):
        h = rtmp.Header()

        self.assertEquals(h.__dict__, {
            'channelId': None,
            'timestamp': None,
            'datatype': None,
            'bodyLength': None,
            'streamId': None,
            'relative': None
        })

    def test_kwargs(self):
        d = {
            'channelId': 1,
            'timestamp': 50,
            'datatype': 20,
            'bodyLength': 2000,
            'streamId': 98,
            'relative': False
        }

        h = rtmp.Header(**d)

        self.assertEquals(h.__dict__, d)

    def test_repr(self):
        h = rtmp.Header()

        self.assertEquals(repr(h), '<rtmpy.rtmp.Header datatype=None '
            'timestamp=None bodyLength=None channelId=None relative=None '
            'streamId=None at 0x%x>' % (id(h),))

        d = {
            'channelId': 1,
            'timestamp': 50,
            'datatype': 20,
            'bodyLength': 2000,
            'streamId': 98,
            'relative': False
        }

        h = rtmp.Header(**d)

        self.assertEquals(repr(h), '<rtmpy.rtmp.Header datatype=20 '
            'timestamp=50 bodyLength=2000 channelId=1 relative=False '
            'streamId=98 at 0x%x>' % (id(h),))


class ChannelTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.Channel}.
    """

    def test_interface(self):
        c = rtmp.Channel()

        self.assertTrue(interfaces.IChannel.providedBy(c))

    def test_init(self):
        c = rtmp.Channel()

        self.assertEquals(c.__dict__, {})

    def test_registerManager(self):
        c = rtmp.Channel()

        e = self.assertRaises(TypeError, c.registerManager, object())
        self.assertEquals(str(e), 'Expected IChannelManager for manager ' \
            '(got <type \'object\'>)')

        m = mocks.ChannelManager()
        self.assertTrue(interfaces.IChannelManager.providedBy(m))
        c.registerManager(m)

        self.assertIdentical(m, c.manager)
