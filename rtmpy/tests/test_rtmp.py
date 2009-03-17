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

        self.assertEquals(c.__dict__, {
            'manager': None,
            'header': None,
            'buffer': None,
            'observer': None
        })

    def test_registerManager(self):
        c = rtmp.Channel()

        e = self.assertRaises(TypeError, c.registerManager, object())
        self.assertEquals(str(e), 'Expected IChannelManager for manager ' \
            '(got <type \'object\'>)')

        m = mocks.ChannelManager()
        self.assertTrue(interfaces.IChannelManager.providedBy(m))
        c.registerManager(m)

        self.assertIdentical(m, c.manager)

    def test_registerObserver(self):
        c = rtmp.Channel()

        e = self.assertRaises(TypeError, c.registerObserver, object())
        self.assertEquals(str(e), 'Expected IChannelObserver for observer ' \
            '(got <type \'object\'>)')

        o = mocks.ChannelObserver()
        self.assertTrue(interfaces.IChannelObserver.providedBy(o))
        c.registerObserver(o)

        self.assertIdentical(o, c.observer)

        # make sure that the observer gets notified if the channel is
        # buffering data.

        c = rtmp.Channel()
        c.buffer = 'hello'

        o = mocks.ChannelObserver()
        c.registerObserver(o)

        self.assertEquals(o.events, [('data-received', 'hello')])
        self.assertEquals(o.buffer, 'hello')

    def test_reset(self):
        c = rtmp.Channel()

        # doing a reset requires a manager
        e = self.assertRaises(rtmp.NoManagerError, c.reset)
        self.assertEquals(str(e), 'Resetting a channel requires a ' \
            'registered manager')

        m = mocks.ChannelManager()
        c.registerManager(m)

        self.assertEquals(c.__dict__, {
            'manager': m,
            'buffer': None,
            'header': None,
            'observer': None
        })

        c.reset()
        self.assertEquals(c.__dict__, {
            'manager': m,
            'frameRemaining': m.frameSize,
            'bodyRemaining': None,
            'buffer': None,
            'bytes': 0,
            'frames': 0,
            'header': None,
            'observer': None
        })

    def test_getHeader(self):
        c = rtmp.Channel()

        self.assertEquals(c.getHeader(), None)

        o = object()
        c.header = o

        self.assertIdentical(c.getHeader(), o)

    def test_repr(self):
        c = rtmp.Channel()

        self.assertEquals(repr(c),
            '<rtmpy.rtmp.Channel header=None at 0x%x>' % (id(c),))

        h = mocks.Header(relative=False, bodyLength=50, datatype=2,
            timestamp=45, channelId=10, streamId=1)

        m = mocks.ChannelManager()
        c.registerManager(m)

        c.setHeader(h)

        self.assertEquals(repr(c),
            '<rtmpy.rtmp.Channel channelId=10 datatype=2 frameRemaining=128' \
                ' frames=0 bytes=0 bodyRemaining=50 at 0x%x>' % (id(c),))


class ChannelHeaderTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.Channel.setHeader}
    """

    def setUp(self):
        self.channel = rtmp.Channel()
        self.manager = mocks.ChannelManager()

        self.channel.registerManager(self.manager)

    def test_interface(self):
        c = rtmp.Channel()

        e = self.assertRaises(TypeError, c.setHeader, object())
        self.assertEquals(str(e), 'Expected header to implement IHeader')

    def test_nomanager(self):
        c = rtmp.Channel()
        h = mocks.Header()
        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertEquals(c.manager, None)

        e = self.assertRaises(rtmp.NoManagerError, c.setHeader, h)
        self.assertEquals(str(e), 'Setting the header requires a ' \
            'registered manager')

    def test_noHeader_setRelative(self):
        self.assertEquals(self.channel.header, None)

        h = mocks.Header(relative=True)
        self.assertTrue(h.relative)

        e = self.assertRaises(rtmp.HeaderError, self.channel.setHeader, h)
        self.assertEquals(str(e), 'Tried to set a relative header as ' \
            'absolute')

    def test_initialiseChannel(self):
        self.assertEquals(self.channel.header, None)

        h = mocks.Header(relative=False, bodyLength=10)
        self.assertFalse(h.relative)

        self.channel.setHeader(h)

        self.assertIdentical(self.channel.header, h)
        # make sure manager.initialiseChannel was callled
        self.assertEquals(self.manager.initialised, [self.channel])

        self.assertEquals(self.channel.bodyRemaining, h.bodyLength)

    def test_absoluteHeader(self):
        a = mocks.Header(relative=False, bodyLength=10, datatype=2,
            timestamp=45, channelId=10, streamId=1)
        r = mocks.Header(relative=True, channelId=10, bodyLength=50)

        self.channel.reset()
        self.channel.header = a

        self.channel.setHeader(r)
        h = self.channel.getHeader()

        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertNotEquals(h, a)

        self.assertEquals(h.bodyLength, 50)
        self.assertEquals(self.channel.bodyRemaining, 50)


class ChannelDataTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.Channel.dataReceived}
    """

    def setUp(self):
        self.channel = rtmp.Channel()
        self.manager = mocks.ChannelManager()
        self.header = mocks.Header(relative=False, bodyLength=50, datatype=2,
            timestamp=45, channelId=10, streamId=1)

        self.manager.channels = {10: self.channel}
        self.channel.registerManager(self.manager)
        self.channel.setHeader(self.header)

    def test_noheader(self):
        c = rtmp.Channel()

        e = self.assertRaises(rtmp.HeaderError, c.dataReceived, '')
        self.assertEquals(str(e), 'Cannot write to a channel with no header')

    def test_buffer(self):
        self.assertEquals(self.channel.observer, None)
        self.assertEquals(self.channel.buffer, None)

        self.channel.dataReceived('hello')
        self.assertEquals(self.channel.buffer, 'hello')

        self.channel.dataReceived(' world')
        self.assertEquals(self.channel.buffer, 'hello world')

    def test_tooMuchData(self):
        self.assertEquals(self.channel.bodyRemaining, 50)
        self.assertEquals(self.channel.bytes, 0)
        e = self.assertRaises(OverflowError,
            self.channel.dataReceived, 'a' * 51)
        self.assertEquals(str(e), 'Attempted to write more data than was ' \
            'expected (attempted:51 remaining:50 total:50)')

    def test_receive(self):
        observer = mocks.ChannelObserver()

        self.channel.registerObserver(observer)

        self.assertEquals(self.channel.buffer, None)
        self.channel.dataReceived('foo bar')

        self.assertEquals(observer.events, [('data-received', 'foo bar')])
        self.assertEquals(observer.buffer, 'foo bar')
        self.assertEquals(self.channel.buffer, None)

    def test_counters(self):
        self.header.bodyLength = 584
        self.manager.frameSize = 128

        self.channel.setHeader(self.header)

        self.assertEquals(self.channel.bytes, 0)
        self.assertEquals(self.channel.frames, 0)
        self.assertEquals(self.channel.frameRemaining, 128)
        self.assertEquals(self.channel.bodyRemaining, 584)

        self.channel.dataReceived('')
        self.assertEquals(self.channel.bytes, 0)
        self.assertEquals(self.channel.frames, 0)
        self.assertEquals(self.channel.frameRemaining, 128)
        self.assertEquals(self.channel.bodyRemaining, 584)

        # write less than one frame
        self.channel.dataReceived('a' * 10)

        self.assertEquals(self.channel.bytes, 10)
        self.assertEquals(self.channel.frames, 0)
        self.assertEquals(self.channel.frameRemaining, 118)
        self.assertEquals(self.channel.bodyRemaining, 574)

        # write just under one frame
        self.channel.dataReceived('a' * 117)

        self.assertEquals(self.channel.bytes, 127)
        self.assertEquals(self.channel.frames, 0)
        self.assertEquals(self.channel.frameRemaining, 1)
        self.assertEquals(self.channel.bodyRemaining, 457)

        # complete the frame
        self.channel.dataReceived('a')
        self.assertEquals(self.channel.bytes, 128)
        self.assertEquals(self.channel.frames, 1)
        self.assertEquals(self.channel.frameRemaining, 128)
        self.assertEquals(self.channel.bodyRemaining, 456)

        # write more than one frame
        self.channel.dataReceived('a' * 150)

        self.assertEquals(self.channel.bytes, 278)
        self.assertEquals(self.channel.frames, 2)
        self.assertEquals(self.channel.frameRemaining, 106)
        self.assertEquals(self.channel.bodyRemaining, 306)

        # complete the frame
        self.channel.dataReceived('a' * 106)

        self.assertEquals(self.channel.bytes, 384)
        self.assertEquals(self.channel.frames, 3)
        self.assertEquals(self.channel.frameRemaining, 128)
        self.assertEquals(self.channel.bodyRemaining, 200)

        # now change the frame size
        self.manager.setFrameSize(200)

        self.assertEquals(self.channel.bytes, 384)
        self.assertEquals(self.channel.frames, 3)
        self.assertEquals(self.channel.frameRemaining, 200)
        self.assertEquals(self.channel.bodyRemaining, 200)

        # write 128 bytes (previous frame size)
        self.channel.dataReceived('a' * 128)
        self.assertEquals(self.channel.bytes, 512)
        self.assertEquals(self.channel.frames, 3)
        self.assertEquals(self.channel.frameRemaining, 72)
        self.assertEquals(self.channel.bodyRemaining, 72)

        # finish the body off, check for firing of complete reset the 
        self.channel.dataReceived('a' * 72)

        self.assertEquals(self.manager.complete, [(10, 'a' * 584)])
        self.assertEquals(self.channel.bytes, 584)
        self.assertEquals(self.channel.frames, 4)
        self.assertEquals(self.channel.frameRemaining, 200)
        self.assertEquals(self.channel.bodyRemaining, 0)
