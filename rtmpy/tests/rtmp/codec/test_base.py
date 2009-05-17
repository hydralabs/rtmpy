# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.codec}.
"""

from twisted.internet import defer, task
from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy.rtmp.codec import header
from rtmpy import util, rtmp

from rtmpy.tests.rtmp import mocks


class ModuleConstTestCase(unittest.TestCase):
    """
    Test for L{codec} module constants
    """

    def test_constants(self):
        self.assertEquals(codec.MAX_CHANNELS, 64)
        self.assertEquals(codec.FRAME_SIZE, 128)


class BaseCodecTestCase(unittest.TestCase):
    """
    Tests for L{codec.BaseCodec}
    """

    @classmethod
    def _getJob(cls):
        return lambda: None

    def setUp(self):
        self._getJob = codec.BaseCodec.getJob
        codec.BaseCodec.getJob = BaseCodecTestCase._getJob

    def tearDown(self):
        codec.BaseCodec.getJob = self._getJob

    def test_job(self):
        c = codec.BaseCodec(None)

        self.assertRaises(NotImplementedError, self._getJob, c)

    def test_init(self):
        c = codec.BaseCodec(None)

        self.assertEquals(c.deferred, None)
        self.assertTrue(isinstance(c.buffer, util.BufferedByteStream))
        self.assertTrue(isinstance(c.job, task.LoopingCall))
        self.assertEquals(c.observer, None)

    def test_registerObserver(self):
        c = codec.BaseCodec(None)

        self.assertEquals(c.observer, None)

        m = mocks.CodecObserver()
        c.registerObserver(m)

        self.assertIdentical(m, c.observer)

    def test_destroy_not_running(self):
        c = codec.BaseCodec(None)

        self.assertFalse(c.job.running)

        c.__del__()

    def test_destroy_running(self):
        self.executed = False
        c = codec.BaseCodec(None)

        def cb(lc):
            self.assertIdentical(c.job, lc)
            self.executed = True

        c.start()
        c.deferred.addCallback(cb)

        self.assertFalse(self.executed)
        c.__del__()
        self.assertTrue(self.executed)

    def test_start(self):
        c = codec.BaseCodec(None)

        job = c.job

        self.assertEquals(c.deferred, None)
        self.assertFalse(job.running)

        x = c.start()

        self.assertEquals(x, None)
        self.assertEquals(job.interval, 0)
        self.assertTrue(job.running)

        y = c.start()
        self.assertEquals(y, None)

    def test_pause(self):
        c = codec.BaseCodec(None)
        job = c.job
        c.deferred = object()

        self.assertFalse(job.running)
        c.pause()
        self.assertFalse(job.running)
        self.assertNotEquals(c.deferred, None)

        c.start()
        self.assertTrue(job.running)

        c.pause()
        self.assertFalse(job.running)
        self.assertEquals(c.deferred, None)

    def test_observer(self):
        c = codec.BaseCodec(None)

        self.assertEquals(c.observer, None)

        o = mocks.CodecObserver()
        c.registerObserver(o)

        self.assertIdentical(c.observer, o)

        self.assertEquals(o.events, [])

        c.start()

        self.assertEquals(o.events, [('start', tuple(), {})])
        o.events = []

        c.pause()
        self.assertEquals(o.events, [('stop', tuple(), {})])


class ChannelManagerTestCase(unittest.TestCase):
    """
    Tests for L{interfaces.IChannelManager} implementation of
    L{codec.BaseCodec}.
    """

    @classmethod
    def _getJob(cls):
        return lambda: None

    def setUp(self):
        self._getJob = codec.BaseCodec.getJob
        self._channelClass = codec.BaseCodec.channel_class
        codec.BaseCodec.getJob = BaseCodecTestCase._getJob

        codec.BaseCodec.channel_class = mocks.Channel

    def tearDown(self):
        codec.BaseCodec.getJob = self._getJob
        codec.BaseCodec.channel_class = self._channelClass

    def test_interface(self):
        self.assertTrue(
            interfaces.IChannelManager.implementedBy(codec.BaseCodec))

    def test_init(self):
        c = codec.BaseCodec(None)

        self.assertEquals(c.channels, {})
        self.assertEquals(c.frameSize, codec.FRAME_SIZE)

    def test_createChannel(self):
        c = codec.BaseCodec(None)

        self.assertEquals(c.channels, {})

        idx = 3
        channel = c.createChannel(idx)

        self.assertTrue(isinstance(channel, mocks.Channel))
        self.assertEquals(c.channels, {idx: channel, channel: idx})
        self.assertIdentical(channel.manager, c)
        self.assertFalse(channel.has_reset)

        e = self.assertRaises(IndexError, c.createChannel, idx)
        self.assertEquals(str(e), 'A channel is already registered to id 3')

        e = self.assertRaises(IndexError, c.createChannel, -1)
        self.assertEquals(str(e), 'channelId is out of range (got:-1)')

        e = self.assertRaises(IndexError, c.createChannel,
            codec.MAX_CHANNELS + 1)
        self.assertEquals(str(e), 'channelId is out of range (got:%d)' % (
            codec.MAX_CHANNELS + 1))

    def test_getChannel(self):
        c = codec.BaseCodec(None)

        self.assertEquals(c.channels, {})
        self.executed = False

        def createChannel(channelId):
            self.channelId = channelId
            self.executed = True

        c.createChannel = createChannel

        # test channel creation
        channel = c.getChannel(10)

        self.assertTrue(self.executed)
        self.assertEquals(self.channelId, 10)

        c = codec.BaseCodec(None)
        self.assertEquals(c.channels, {})

        channel = c.getChannel(10)
        self.assertTrue(isinstance(channel, mocks.Channel))
        self.assertEquals(channel.manager, c)
        self.assertEquals(c.channels, {10: channel, channel: 10})

        c.createChannel = createChannel
        self.executed = False
        channel2 = c.getChannel(10)

        self.assertFalse(self.executed)
        self.assertIdentical(channel, channel2)

    def test_getNextAvailableChannelId(self):
        c = codec.BaseCodec(None)

        channels = []

        for x in xrange(0, codec.MAX_CHANNELS):
            channels.append(x)

        c.activeChannels = channels
        self.assertEquals(len(channels), codec.MAX_CHANNELS)
        e = self.assertRaises(OverflowError, c.getNextAvailableChannelId)
        self.assertEquals(str(e), 'No free channel')

        c = codec.BaseCodec(None)

        self.assertEquals(c.activeChannels, [])
        self.assertEquals(c.getNextAvailableChannelId(), 0)

        c.activeChannels = [0]
        self.assertEquals(c.getNextAvailableChannelId(), 1)

        c.activeChannels = [0, 3, 1]
        self.assertEquals(c.getNextAvailableChannelId(), 2)
        c.activeChannels.append(2)
        self.assertEquals(c.getNextAvailableChannelId(), 4)

        channels = []

        for x in xrange(0, codec.MAX_CHANNELS - 1):
            channels.append(x)

        c.activeChannels = channels
        self.assertEquals(c.getNextAvailableChannelId(), codec.MAX_CHANNELS - 1)

    def test_channelComplete(self):
        c = codec.BaseCodec(None)
        m = mocks.ChannelManager()

        channel = mocks.Channel(m)
        header = mocks.Header(channelId=3, relative=False)

        channel.setHeader(header)
        c.channels = {3: channel}

        self.assertFalse(3 in c.activeChannels)
        c.activeChannels.append(3)
        c.channelComplete(channel)

        self.assertEquals(c.channels, {3: channel})
        self.assertTrue(channel.has_reset)
        self.assertEquals(c.activeChannels, [3])

        # test bodyComplete
        c = codec.BaseCodec(None)

        channel = mocks.Channel(None)
        header = mocks.Header(channelId=10, relative=False)

        channel.manager = mocks.ChannelManager()

        channel.setHeader(header)
        c.channels = {10: channel}
        c.activeChannels = [10]

        c.channelComplete(channel)

        self.assertEquals(c.activeChannels, [10])

    def test_initialiseChannel(self):
        channel = mocks.Channel(None)
        c = codec.BaseCodec(None)

        self.assertNotEquals(channel.manager, c)
        e = self.assertRaises(ValueError, c.initialiseChannel, channel, None)
        self.assertEquals(str(e), "Cannot initialise a channel that isn't "
            "registered to this manager")

        self.assertFalse(channel.has_reset)
        self.assertEquals(c.activeChannels, [])

        channel.manager = c

        channel.header = mocks.Header(channelId=68)

        self.assertEquals(c.activeChannels, [])
        c.initialiseChannel(channel, None)

        self.assertTrue(channel.has_reset)
        self.assertEquals(c.activeChannels, [])

    def test_setFrameSize(self):
        c = codec.BaseCodec(None)
        self.assertNotEquals(c.frameSize, 100)

        c.setFrameSize(100)
        self.assertEquals(c.frameSize, 100)

        c = codec.BaseCodec(None)
        c.channels = {10: mocks.Channel(c), 85: mocks.Channel(c)}
        self.assertNotEquals(c.frameSize, 100)

        c.activeChannels.append(85)

        c.setFrameSize(100)

        self.assertFalse(hasattr(c.channels[10], 'frameRemaining'))
        self.assertEquals(c.channels[85].frameRemaining, 100)

    def test_activateChannel(self):
        c = codec.BaseCodec(None)

        channel = mocks.Channel(None)

        self.assertFalse(channel in c.channels)
        e = self.assertRaises(RuntimeError, c.activateChannel, channel)
        self.assertEquals(str(e), 'Channel is not registered to this codec')

        c.channels = {channel: 0, 0: channel}
        c.activeChannels = []

        c.activateChannel(channel)

        self.assertEquals(c.activeChannels, [0])
        self.assertEquals(c.channels, {channel: 0, 0: channel})

        c.activateChannel(channel)

        self.assertEquals(c.activeChannels, [0])
        self.assertEquals(c.channels, {channel: 0, 0: channel})

    def test_deactivateChannel(self):
        c = codec.BaseCodec(None)

        channel = mocks.Channel(None)

        self.assertFalse(channel in c.channels)
        e = self.assertRaises(RuntimeError, c.activateChannel, channel)
        self.assertEquals(str(e), 'Channel is not registered to this codec')

        c.channels = {channel: 0, 0: channel}
        c.activeChannels = []

        c.deactivateChannel(channel)

        self.assertEquals(c.activeChannels, [])
        self.assertEquals(c.channels, {channel: 0, 0: channel})

        c.activeChannels = [0]
        c.deactivateChannel(channel)

        self.assertEquals(c.activeChannels, [])
        self.assertEquals(c.channels, {channel: 0, 0: channel})


class ChannelTestCase(unittest.TestCase):
    """
    Tests for L{codec.Channel}.
    """

    def test_interface(self):
        c = codec.Channel(None)

        self.assertTrue(interfaces.IChannel.providedBy(c))

    def test_init(self):
        c = codec.Channel(None)

        self.assertEquals(c.__dict__, {
            'manager': None,
            'header': None,
            'buffer': None,
            'observer': None,
            'debug': rtmp.DEBUG
        })

    def test_registerObserver(self):
        c = codec.Channel(None)

        o = mocks.ChannelObserver()
        self.assertTrue(interfaces.IChannelObserver.providedBy(o))
        c.registerObserver(o)

        self.assertIdentical(o, c.observer)

    def test_reset(self):
        m = mocks.ChannelManager()
        c = codec.Channel(m)

        self.assertEquals(c.__dict__, {
            'manager': m,
            'buffer': None,
            'header': None,
            'observer': None,
            'debug': rtmp.DEBUG
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
            'observer': None,
            'debug': rtmp.DEBUG
        })

    def test_getHeader(self):
        c = codec.Channel(None)

        self.assertEquals(c.getHeader(), None)

        o = object()
        c.header = o

        self.assertIdentical(c.getHeader(), o)

    def test_repr(self):
        c = codec.Channel(None)

        self.assertEquals(repr(c),
            '<rtmpy.rtmp.codec.Channel header=None at 0x%x>' % (id(c),))

        h = mocks.Header(relative=False, bodyLength=50, datatype=2,
            timestamp=45, channelId=10, streamId=1)

        m = c.manager = mocks.ChannelManager()

        c.setHeader(h)

        self.assertEquals(repr(c), '<rtmpy.rtmp.codec.Channel channelId=10 '
            'datatype=2 frameRemaining=128 frames=0 bytes=0 bodyRemaining=50 '
            'at 0x%x>' % (id(c),))


class ChannelObserverTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.manager = mocks.ChannelManager()
        self.channel = codec.Channel(self.manager)
        self.observer = mocks.ChannelObserver()

        self.channel.registerObserver(self.observer)

    def test_buffering(self):
        # make sure that the observer gets notified if the channel is
        # buffering data.

        c = codec.Channel(None)
        c.buffer = 'hello'

        o = mocks.ChannelObserver()
        c.registerObserver(o)

        self.assertEquals(o.events, [('data-received', 'hello')])
        self.assertEquals(o.buffer, 'hello')

    def test_dataReceived(self):
        self.channel.setHeader(mocks.Header(relative=False, bodyLength=50))
        # test dataReceived

        self.channel.dataReceived('foo')

        self.assertEquals(self.observer.events, [('data-received', 'foo')])

    def test_headerChanged(self):
        h = mocks.Header(relative=False, channelId=4, bodyLength=400)
        self.channel.setHeader(h)

        self.assertEquals(self.observer.events, [])

        h = mocks.Header(relative=True, channelId=4, bodyLength=7000)

        self.channel.setHeader(h)
        self.assertNotEquals(h, self.channel.header)

        self.assertEquals(self.observer.events, [('header-changed', self.channel.header)])

    def test_bodyComplete(self):
        h = mocks.Header(relative=False, channelId=4, bodyLength=400)
        self.channel.setHeader(h)

        self.assertEquals(self.observer.events, [])
        self.channel.dataReceived('a' * 400)

        self.assertEquals(self.observer.events, [
            ('data-received', 'a' * 400),
            ('body-complete',)
        ])


class ChannelHeaderTestCase(unittest.TestCase):
    """
    Tests for L{codec.Channel.setHeader}
    """

    def setUp(self):
        self.manager = mocks.ChannelManager()
        self.channel = codec.Channel(self.manager)

    def test_interface(self):
        c = codec.Channel(None)

        self.assertTrue(interfaces.IChannel.providedBy(c))

    def test_nomanager(self):
        c = codec.Channel(None)
        h = mocks.Header(relative=False)
        self.assertEquals(c.manager, None)

        e = self.assertRaises(AttributeError, c.setHeader, h)
        self.assertEquals(str(e), "'NoneType' object has no attribute "
            "'initialiseChannel'")

    def test_noHeader_setRelative(self):
        self.assertEquals(self.channel.header, None)

        h = mocks.Header(relative=True)
        self.assertTrue(h.relative)

        e = self.assertRaises(header.HeaderError, self.channel.setHeader, h)
        self.assertEquals(str(e), 'Tried to set a relative header as '
            'absolute')

    def test_initialiseChannel(self):
        self.assertEquals(self.channel.header, None)

        h = mocks.Header(channelId=34, bodyLength=10, relative=False)
        self.assertFalse(h.relative)

        self.channel.setHeader(h)
        self.assertEquals(self.manager.channel_headers, {self.channel: [None]})

        self.assertIdentical(self.channel.header, h)
        # make sure manager.initialiseChannel was called
        self.assertEquals(self.manager.initialised, [self.channel])

        self.assertEquals(self.channel.bodyRemaining, h.bodyLength)

        oldHeader, h = h, mocks.Header(channelId=34, bodyLength=10, relative=False)

        self.channel.setHeader(h)
        self.assertEquals(self.manager.channel_headers, {
            self.channel: [None, oldHeader]
        })

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

    def test_differentChannelIds(self):
        a = mocks.Header(channelId=10)
        b = mocks.Header(channelId=11)

        self.channel.header = a

        e = self.assertRaises(header.HeaderError, self.channel.setHeader, b)
        self.assertEquals(str(e), 'Tried to assign a header from a different '
            'channel (original:10, new:11)')


class ChannelDataTestCase(unittest.TestCase):
    """
    Tests for L{codec.Channel.dataReceived}
    """

    def setUp(self):
        self.manager = mocks.ChannelManager()
        self.channel = codec.Channel(self.manager)
        self.header = mocks.Header(relative=False, bodyLength=50, datatype=2,
            timestamp=45, channelId=10, streamId=1)

        self.manager.channels = {10: self.channel}
        self.channel.setHeader(self.header)

    def test_noheader(self):
        c = codec.Channel(None)

        e = self.assertRaises(header.HeaderError, c.dataReceived, '')
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

        self.assertEquals(observer.events,
            [('data-received', 'foo bar')])
        self.assertEquals(observer.buffer, 'foo bar')
        self.assertEquals(self.channel.buffer, None)

    def test_counters(self):
        self.header.bodyLength = 584
        self.manager.frameSize = 128

        self.executed = False

        def complete():
            self.executed = True

        self.channel.onComplete = complete

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

        self.assertEquals(self.channel.bytes, 584)
        self.assertEquals(self.channel.frames, 4)
        self.assertEquals(self.channel.frameRemaining, 200)
        self.assertEquals(self.channel.bodyRemaining, 0)

        self.assertTrue(self.executed)
