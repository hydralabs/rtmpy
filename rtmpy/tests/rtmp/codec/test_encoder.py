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

        c = mocks.Channel(self.manager)
        c.setHeader(h)

        return c

class ChannelContextTestCase(BaseEncoderTestCase):
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

        self.assertTrue(
            isinstance(self.context.buffer, util.BufferedByteStream))
        self.assertFalse(self.context.active)
        self.assertEquals(self.context.header, None)
        self.assertEquals(self.context.bytes, 0)

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


class MinimumFrameSizeTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext.getMinimumFrameSize}.
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self._generateChannel()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.manager.frameSize = 128

    def test_lessThanFrameSize(self):
        self.channel.bytes = 50

        self.assertEquals(self.context.getMinimumFrameSize(), 50)

    def test_lessThanBodyLength(self):
        self.channel.bytes = 500

        self.assertEquals(
            self.context.getMinimumFrameSize(), self.manager.frameSize)

    def test_written(self):
        self.context.bytes = 128
        self.channel.bytes = 178

        self.assertEquals(self.context.getMinimumFrameSize(), 50)

    def test_bad(self):
        self.channel.bytes = -10

        self.assertEquals(self.context.getMinimumFrameSize(), 0)

        self.channel.bytes = 3445
        self.manager.frameSize = 0

        self.assertEquals(self.context.getMinimumFrameSize(), 0)


class GetDataTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext.getData}
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self._generateChannel()
        self.header = self.channel.getHeader()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.context.active = True
        self.encoder.channelContext = {self.channel: self.context}
        self.buffer = self.context.buffer

        self.scheduler.activateChannel(self.channel)
        self.header.bodyLength = 150

    def test_empty(self):
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(self.context.getFrame(), None)
        self.assertFalse(self.context.active)
        self.assertEquals(self.scheduler.activeChannels, [])

    def test_read(self):
        self.channel.write('a' * 150)

        self.assertEquals(self.context.getFrame(), 'a' * 128)
        self.assertEquals(self.buffer.getvalue(), 'a' * 22)
        self.assertTrue(self.context.active)
        self.assertEquals(self.scheduler.activeChannels, [self.channel])

    def test_under(self):
        self.buffer.write('a' * 128)
        self.buffer.seek(10)

        self.assertEquals(self.context.getFrame(), None)
        self.assertEquals(self.buffer.getvalue(), 'a' * 128)
        self.assertFalse(self.context.active)
        self.assertEquals(self.scheduler.activeChannels, [])
        self.assertEquals(self.buffer.tell(), 10)


class EncoderTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder}
    """

    def test_init(self):
        e = codec.Encoder(self.manager)

        self.assertEquals(e.channelContext, {})
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

        self.assertFalse(channel in self.encoder.channelContext)
        self.assertFalse(channel in self.scheduler.activeChannels)

        self.encoder.activateChannel(channel)
        self.assertTrue(channel in self.encoder.channelContext)
        self.assertTrue(channel in self.scheduler.activeChannels)

    def test_deactivateChannel(self):
        channel = self._generateChannel()

        self.assertFalse(channel in self.encoder.channelContext.keys())
        self.assertFalse(channel in self.scheduler.activeChannels)

        e = self.assertRaises(
            RuntimeError, self.encoder.deactivateChannel, channel)
        self.assertEquals(str(e), 'Attempted to deactivate a ' \
            'non-existant channel')

        context = codec.ChannelContext(channel, self.encoder)

        self.encoder.channelContext[channel] = context
        self.encoder.activateChannel(channel)

        self.assertTrue(channel in self.encoder.channelContext.keys())

        self.encoder.deactivateChannel(channel)
        self.assertFalse(channel in self.scheduler.activeChannels)

    def test_nochannel(self):
        self.assertEquals(self.scheduler.getNextChannel(), None)
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertFalse(self.encoder.job.running)

    def test_single(self):
        ch = self._generateChannel()
        h = ch.getHeader()
        h.bodyLength = 50
        h.datatype = 4
        h.streamId = 8
        h.relative = False
        h.timestamp = 2341234

        self.encoder.activateChannel(ch)
        context = self.encoder.channelContext[ch]
        ch.write('f' * 50)

        self.assertEquals(self.scheduler.getNextChannel(), ch)

        def cb(lc):
            self.assertEquals(self.buffer.getvalue(),
                '\x00#\xb9r\x00\x002\x04\x00\x00\x00\x08' + ('f' * 50))

            self.assertEquals(self.encoder.buffer.getvalue(), '')

        return self.encoder.start().addCallback(cb)

class FrameWritingTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder.writeFrame}
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.buffer = self.encoder.buffer
        self.contexts = self.encoder.channelContext
        self.manager.frameSize = 128

    def _generateContext(self, bodyLength=1000):
        channel = self._generateChannel()
        header = channel.getHeader()

        header.bodyLength = bodyLength

        self.encoder.activateChannel(channel)

        return self.contexts[channel]

    def test_nodata(self):
        context = self._generateContext()
        channel = context.channel

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(
            min(channel.bodyRemaining, self.manager.frameSize), 128)
        self.assertEquals(context.getFrame(), None)

        self.encoder.writeFrame(context)
        self.assertEquals(self.buffer.getvalue(), '')

    def test_data(self):
        context = self._generateContext()
        channel = context.channel
        header = channel.getHeader()

        header.streamId = 70
        header.datatype = 3
        header.relative = False
        header.timestamp = 13123

        channel.write('a' * 200)

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(
            min(channel.bodyRemaining, self.manager.frameSize), 128)

        self.encoder.writeFrame(context)
        self.assertEquals(self.buffer.getvalue(), '\x00\x003C\x00\x03\xe8\x03'
            '\x00\x00\x00F' + ('a' * self.manager.frameSize))

        self.assertEquals(context.buffer.getvalue(), 'a' * 72)
        self.assertIdentical(context.header, header)

        self.assertEquals(
            min(channel.bodyRemaining, self.manager.frameSize), 128)

        self.encoder.writeFrame(context)

        self.assertEquals(self.buffer.getvalue(), '\x00\x003C\x00\x03\xe8\x03'
            '\x00\x00\x00Faaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            'aaaaaaaaaaaaa\xc0aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            'aaaaaaaaaaaaaaaaaaaaaaaaa')
