# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.codec}.
"""

from twisted.internet import defer, task
from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy import util

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
        c = codec.BaseCodec()

        self.assertRaises(NotImplementedError, self._getJob, c)

    def test_init(self):
        c = codec.BaseCodec()

        self.assertEquals(c.deferred, None)
        self.assertTrue(isinstance(c.buffer, util.BufferedByteStream))
        self.assertTrue(isinstance(c.job, task.LoopingCall))

    def test_destroy_not_running(self):
        c = codec.BaseCodec()

        self.assertFalse(c.job.running)

        c.__del__()

    def test_destroy_running(self):
        self.executed = False
        c = codec.BaseCodec()

        def cb(lc):
            self.assertIdentical(c.job, lc)
            self.executed = True

        c.start().addCallback(cb)

        self.assertFalse(self.executed)
        c.__del__()
        self.assertTrue(self.executed)

    def test_start(self):
        c = codec.BaseCodec()

        job = c.job

        self.assertEquals(c.deferred, None)
        self.assertFalse(job.running)

        x = c.start()

        self.assertTrue(x, defer.Deferred)
        self.assertIdentical(c.deferred, x)
        self.assertEquals(job.interval, 0)
        self.assertTrue(job.running)

        y = c.start()
        self.assertIdentical(c.deferred, x, y)

    def test_pause(self):
        c = codec.BaseCodec()
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
        c = codec.BaseCodec()

        self.assertEquals(c.channels, {})
        self.assertEquals(c.frameSize, codec.FRAME_SIZE)

    def test_createChannel(self):
        c = codec.BaseCodec()

        self.assertEquals(c.channels, {})

        idx = 3
        channel = c.createChannel(idx)

        self.assertTrue(isinstance(channel, mocks.Channel))
        self.assertEquals(c.channels, {idx: channel})
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
        c = codec.BaseCodec()

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

        c = codec.BaseCodec()
        self.assertEquals(c.channels, {})

        channel = c.getChannel(10)
        self.assertTrue(isinstance(channel, mocks.Channel))
        self.assertEquals(channel.manager, c)
        self.assertEquals(c.channels, {10: channel})

        c.createChannel = createChannel
        self.executed = False
        channel2 = c.getChannel(10)

        self.assertFalse(self.executed)
        self.assertIdentical(channel, channel2)

    def test_getNextAvailableChannelId(self):
        c = codec.BaseCodec()

        channels = {}

        for x in xrange(0, codec.MAX_CHANNELS):
            channels[x] = None

        c.channels = channels
        self.assertEquals(len(channels.keys()), codec.MAX_CHANNELS)
        e = self.assertRaises(OverflowError, c.getNextAvailableChannelId)
        self.assertEquals(str(e), 'No free channel')

        c = codec.BaseCodec()

        self.assertEquals(c.channels, {})
        self.assertEquals(c.getNextAvailableChannelId(), 0)

        c.channels = {0: None}
        self.assertEquals(c.getNextAvailableChannelId(), 1)

        c.channels = {0: None, 1: None, 3: None}
        self.assertEquals(c.getNextAvailableChannelId(), 2)
        c.channels[2] = None
        self.assertEquals(c.getNextAvailableChannelId(), 4)

        channels = {}

        for x in xrange(0, codec.MAX_CHANNELS - 1):
            channels[x] = None

        c.channels = channels
        self.assertEquals(c.getNextAvailableChannelId(), codec.MAX_CHANNELS - 1)

    def test_channelComplete(self):
        # TODO: complete me
        pass

    def test_initialiseChannel(self):
        channel = mocks.Channel()
        channel.manager = None
        c = codec.BaseCodec()

        self.assertNotEquals(channel.manager, c)
        e = self.assertRaises(ValueError, c.initialiseChannel, channel)
        self.assertEquals(str(e), "Cannot initialise a channel that isn't "
            "registered to this manager")

        self.assertFalse(channel.has_reset)

        channel.registerManager(c)
        c.initialiseChannel(channel)

        self.assertTrue(channel.has_reset)

    def test_setFrameSize(self):
        c = codec.BaseCodec()
        self.assertNotEquals(c.frameSize, 100)

        c.setFrameSize(100)
        self.assertEquals(c.frameSize, 100)

        c = codec.BaseCodec()
        c.channels = {10: mocks.Channel(), 85: mocks.Channel()}
        self.assertNotEquals(c.frameSize, 100)

        c.setFrameSize(100)

        self.assertEquals(c.channels[10].frameRemaining, 100)
        self.assertEquals(c.channels[85].frameRemaining, 100)
