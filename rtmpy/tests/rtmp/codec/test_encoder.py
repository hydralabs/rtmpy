# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Encoding tests for L{rtmpy.rtmp.codec}.
"""

from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy import util
from rtmpy.tests.rtmp import mocks


class BaseEncoderTestCase(unittest.TestCase):
    """
    Base functionality for other unit tests.
    """

    def setUp(self):
        self.manager = mocks.ChannelManager()
        self.encoder = codec.Encoder(self.manager)
        self.scheduler = mocks.LoopingScheduler()

        self.buffer = util.BufferedByteStream()

        self.encoder.registerScheduler(self.scheduler)
        self.encoder.registerConsumer(self.buffer)

        self._channelId = 0

    def _generateChannel(self):
        """
        Generates a unique channel.
        """
        h = mocks.Header(channelId=self._channelId, relative=False)
        self._channelId += 1

        c = mocks.Channel()
        c.setHeader(h)

        return c

class ClassContextTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext}.
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self._generateChannel()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.buffer = self.context.buffer

    def test_init(self):
        self.assertIdentical(self.context.channel, self.channel)
        self.assertIdentical(self.context.encoder, self.encoder)

        self.assertTrue(isinstance(self.context.buffer, util.BufferedByteStream))
        self.assertFalse(self.context.active)
        self.assertEquals(self.context.header, None)

        self.assertIdentical(self.context, self.channel.consumer)

    def test_write(self):
        self.assertFalse(self.context.active)
        self.assertEquals(self.buffer.tell(), 0)

        self.encoder.activeChannels = set([self.channel])
        self.encoder.channelContext = {self.channel: self.context}

        self.context.write('hello')
        self.assertTrue(self.context.active)
        self.assertEquals(self.buffer.getvalue(), 'hello')
        self.assertEquals(self.buffer.tell(), 5)

        self.assertEquals(self.encoder.activeChannels, set([self.channel]))

    def test_getRelativeHeader(self):
        h = mocks.Header(relative=False, channelId=3, bodyLength=50,
            timestamp=10)
        self.channel.setHeader(h)

        self.assertIdentical(self.context.getRelativeHeader(), h)
        self.assertIdentical(self.context.header, None)

        self.context.header = mocks.Header(relative=False, channelId=3,
            bodyLength=10, timestamp=2)

        h = self.context.getRelativeHeader()

        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertTrue(h.relative)


class GetDataTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext.getData}
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self._generateChannel()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.context.active = True
        self.encoder.channelContext = {self.channel: self.context}
        self.buffer = self.context.buffer

        self.scheduler.activateChannel(self.channel)

    def test_empty(self):
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(self.context.getData(1), None)
        self.assertFalse(self.context.active)
        self.assertEquals(self.scheduler.activeChannels, {})

    def test_read(self):
        self.buffer.write('foobar')
        self.buffer.seek(0)

        self.assertEquals(self.context.getData(1), 'f')
        self.assertEquals(self.buffer.getvalue(), 'oobar')
        self.assertTrue(self.context.active)
        self.assertEquals(self.scheduler.activeChannels, {0: self.channel})

    def test_under(self):
        self.buffer.write('foobar')
        self.buffer.seek(2)

        self.assertEquals(self.context.getData(10), None)
        self.assertEquals(self.buffer.getvalue(), 'foobar')
        self.assertFalse(self.context.active)
        self.assertEquals(self.scheduler.activeChannels, {})
        self.assertEquals(self.buffer.tell(), 2)


class EncoderTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder}
    """

    def test_init(self):
        e = codec.Encoder(self.manager)

        self.assertEquals(e.channelContext, {})
        self.assertEquals(e.currentContext, None)
        self.assertEquals(e.consumer, None)
        self.assertEquals(e.scheduler, None)

    def test_job(self):
        self.assertEquals(self.encoder.getJob(), self.encoder.encode)

    def test_registerScheduler(self):
        e = codec.Encoder(self.manager)

        s = mocks.LoopingScheduler()

        self.assertTrue(interfaces.IChannelScheduler.providedBy(s))
        self.assertEquals(e.scheduler, None)

        r = self.assertRaises(TypeError, e.registerScheduler, object())
        self.assertEquals(str(r), 'Expected IChannelScheduler interface')

        e.registerScheduler(s)
        self.assertIdentical(e.scheduler, s)

    def test_registerConsumer(self):
        consumer = object()

        self.encoder.registerConsumer(consumer)
        self.assertIdentical(consumer, self.encoder.consumer)

        otherConsumer = object()

        self.encoder.registerConsumer(otherConsumer)
        self.assertIdentical(otherConsumer, self.encoder.consumer)

    def test_activateChannel(self):
        channel = self._generateChannel()

        self.assertFalse(channel in self.encoder.channelContext.keys())
        self.assertFalse(channel in self.scheduler.activeChannels)

        e = self.assertRaises(RuntimeError, self.encoder.activateChannel, channel)
        self.assertEquals(str(e), 'Attempted to activate a non-existant channel')

        self.encoder.channelContext = {channel: 'foo'}
        self.assertFalse(channel in self.scheduler.activeChannels)

        self.encoder.activateChannel(channel)
        self.assertTrue(channel in self.scheduler.activeChannels.values())

    def test_deactivateChannel(self):
        channel = self._generateChannel()

        self.assertFalse(channel in self.encoder.channelContext.keys())
        self.assertFalse(channel in self.scheduler.activeChannels)

        e = self.assertRaises(RuntimeError, self.encoder.deactivateChannel, channel)
        self.assertEquals(str(e), 'Attempted to deactivate a non-existant channel')

        context = codec.ChannelContext(channel, self.encoder)

        self.encoder.channelContext[channel] = context
        self.encoder.activateChannel(channel)

        self.assertTrue(channel in self.encoder.channelContext.keys())

        self.encoder.deactivateChannel(channel)
        self.assertFalse(channel in self.scheduler.activeChannels.values())

    def test_getMinimumFrameSize(self):
        channel = self._generateChannel()
        header = channel.getHeader()
        header.bodyLength = 50
        self.manager.frameSize = 128

        self.assertTrue(header.bodyLength < self.manager.frameSize)
        self.assertEquals(self.encoder.getMinimumFrameSize(channel), 50)

        header.bodyLength = 500

        self.assertTrue(header.bodyLength > self.manager.frameSize)
        self.assertEquals(
            self.encoder.getMinimumFrameSize(channel), self.manager.frameSize)

        header.bodyLength = -10
        e = self.assertRaises(
            RuntimeError, self.encoder.getMinimumFrameSize, channel)

        self.assertEquals(str(e), '-10 bytes (< 1) are available for frame ' \
            '(channel:-10, manager:128)')

        header.bodyLength = 3445
        self.manager.frameSize = 0
        e = self.assertRaises(
            RuntimeError, self.encoder.getMinimumFrameSize, channel)

        self.assertEquals(str(e), '0 bytes (< 1) are available for frame ' \
            '(channel:3445, manager:0)')
