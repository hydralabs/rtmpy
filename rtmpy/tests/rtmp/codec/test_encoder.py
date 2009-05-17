# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Encoding tests for L{rtmpy.rtmp.codec}.
"""

from twisted.trial import unittest
from twisted.internet import defer

from rtmpy.rtmp import codec, interfaces
from rtmpy import util
from rtmpy.tests.rtmp import mocks


class BaseEncoderTestCase(unittest.TestCase):
    """
    Base functionality for other unit tests.
    """

    def setUp(self):
        self.manager = mocks.StreamManager()
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
        c = self.encoder.getChannel(self._channelId)
        h = mocks.Header(channelId=self._channelId, bodyLength=0, relative=False)
        self._channelId += 1

        c.reset()
        c.setHeader(h)

        return c

    def dataReceived(self, data):
        self.buffer.write(data)


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
        self.assertEquals(self.context.queue, [])
        self.assertEquals(self.context.currentPacket, None)
        self.assertEquals(self.context.header, None)

        self.assertFalse(hasattr(self.context, 'bytes'))
        self.assertFalse(hasattr(self.context, 'requiredBytes'))

    def test_reset(self):
        h = mocks.Header(relative=False, channelId=3, bodyLength=50,
            timestamp=10)

        self.context.reset(h)

        self.assertEquals(self.context.header, None)
        self.assertEquals(self.context.bytesRequired, 50)
        self.assertEquals(self.context.bytes, 0)
        self.assertEquals(self.buffer.getvalue(), '')

    def test_write(self):
        self.assertEquals(self.buffer.tell(), 0)

        self.encoder.activeChannels = [0]
        self.encoder.channelContext = {self.channel: self.context}

        self.context.dataReceived('hello')
        self.assertEquals(self.buffer.getvalue(), 'hello')
        self.assertEquals(self.buffer.tell(), 5)

        self.assertEquals(self.encoder.activeChannels, [0])

    def test_getRelativeHeader(self):
        h = mocks.Header(relative=False, channelId=0, bodyLength=50,
            timestamp=10)
        self.channel.setHeader(h)

        self.assertIdentical(self.context.getRelativeHeader(), h)
        self.assertIdentical(self.context.header, None)

        self.context.header = mocks.Header(relative=False, channelId=0,
            bodyLength=10, timestamp=2)

        h = self.context.getRelativeHeader()

        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertTrue(h.relative)

        self.assertEquals(h.datatype, None)
        self.assertEquals(h.timestamp, 2)
        self.assertEquals(h.bodyLength, 10)
        self.assertEquals(h.channelId, 0)
        self.assertEquals(h.streamId, None)

    def test_bufferError(self):
        self.executed = False

        class ReadErroringBuffer(object):
            error_class = IOError

            def read(self, *args, **kwargs):
                raise ReadErroringBuffer.error_class

            def seek(self, *args, **kwargs):
                pass

        def deactivateChannel(channel):
            self.executed = True

        self.context.buffer = ReadErroringBuffer()
        self.context.getMinimumFrameSize = lambda: 10

        self.encoder.deactivateChannel = deactivateChannel

        self.assertRaises(IOError, self.context.buffer.read, 0)

        self.context.getFrame()
        self.assertTrue(self.executed)

        self.executed = False
        ReadErroringBuffer.error_class = IOError

        self.context.getFrame()
        self.assertTrue(self.executed)

    def test_headerChange(self):
        """
        Tests relative header changes.
        """
        h = mocks.Header(relative=False, channelId=3, bodyLength=50)

        self.context.reset(h)
        self.assertEquals(self.context.bytesRequired, 50)

        h = mocks.Header(relative=True, bodyLength=100)

        self.context.headerChanged(h)

        self.assertEquals(self.context.bytesRequired, 100)

    def test_deactivateWithQueue(self):
        """
        Test to ensure that a L{ChannelContext} does not deactivate itself
        if there are items in the queue.
        """
        self.encoder.activateChannel(self.channel)

        self.assertEquals(self.encoder.activeChannels, [0])
        self.context.queue = [None]
        h = mocks.Header(relative=False, channelId=3, bodyLength=50)

        self.context.reset(h)

        self.assertEquals(self.context.getFrame(), None)
        self.assertEquals(self.context.queue, [None])

        self.assertEquals(self.encoder.deferred, None)
        self.assertFalse(self.encoder.job.running)


class MinimumFrameSizeTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext.getMinimumFrameSize}.
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self._generateChannel()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.header = self.channel.getHeader()

        self.header.bodyLength = 178
        self.encoder.frameSize = 128

        self.context.reset(self.header)

    def test_lessThanFrameSize(self):
        self.context.bytes = 100

        self.assertEquals(self.context.getMinimumFrameSize(), 78)

    def test_lessThanBodyLength(self):
        self.channel.bytes = 10

        self.assertEquals(self.context.getMinimumFrameSize(), 128)

    def test_bad(self):
        self.channel.bytes = 3445
        self.encoder.frameSize = 0

        self.assertEquals(self.context.getMinimumFrameSize(), 0)

    def test_negative(self):
        self.context.bytesRequired = -100
        self.context.bytes = 0

        e = self.assertRaises(RuntimeError, self.context.getMinimumFrameSize)
        self.assertEquals(str(e), 'getMinimumFrameSize wanted to return -100')


class GetDataTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext.getData}
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self._generateChannel()
        self.header = self.channel.getHeader()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.encoder.channelContext = {self.channel: self.context}
        self.buffer = self.context.buffer

        self.header.bodyLength = 150

        self.context.reset(self.header)

    def test_empty(self):
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(self.context.getFrame(), None)
        self.assertEquals(self.scheduler.activeChannels, [])

    def test_read(self):
        self.context.dataReceived('a' * 150)

        self.assertEquals(self.context.getFrame(), 'a' * 128)
        self.assertEquals(self.buffer.getvalue(), 'a' * 22)
        self.assertEquals(self.scheduler.activeChannels, [self.channel])

    def test_under(self):
        self.context.dataReceived('a' * 10)

        self.assertEquals(self.context.getFrame(), None)
        self.assertEquals(self.buffer.getvalue(), 'a' * 10)
        self.assertEquals(self.scheduler.activeChannels, [])


class EncoderTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder}
    """

    def test_init(self):
        e = codec.Encoder(None)

        self.assertEquals(e.channelContext, {})
        self.assertEquals(e.consumer, None)
        self.assertEquals(e.scheduler, None)

    def test_job(self):
        self.assertEquals(self.encoder.getJob(), self.encoder.encode)

    def test_registerScheduler(self):
        e = codec.Encoder(None)
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
        channel = self.encoder.getChannel(0)

        self.assertTrue(channel in self.encoder.channelContext)
        self.assertFalse(channel in self.encoder.activeChannels)
        self.assertFalse(channel in self.scheduler.activeChannels)

        self.encoder.activateChannel(channel)
        self.assertTrue(channel in self.encoder.channelContext)
        self.assertTrue(0 in self.encoder.activeChannels)
        self.assertTrue(channel in self.scheduler.activeChannels)

    def test_deactivateChannel(self):
        channel = self.encoder.getChannel(0)

        self.assertTrue(channel in self.encoder.channelContext)
        self.assertFalse(channel in self.encoder.activeChannels)
        self.assertFalse(channel in self.scheduler.activeChannels)

        e = self.assertEquals(self.encoder.deactivateChannel(channel), None)

        self.encoder.activateChannel(channel)

        self.assertTrue(channel in self.encoder.channelContext)

        self.encoder.deactivateChannel(channel)
        self.assertFalse(channel in self.scheduler.activeChannels)

    def test_nochannel(self):
        self.assertEquals(self.scheduler.getNextChannel(), None)
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertFalse(self.encoder.job.running)

    def test_single(self):
        ch = self.encoder.getChannel(0)

        h = mocks.Header(bodyLength=50, datatype=4, streamId=8, channelId=0,
            relative=False, timestamp=2341234)

        ch.setHeader(h)

        self.assertEquals(self.encoder.activeChannels, [])
        context = self.encoder.channelContext[ch]
        ch.dataReceived('f' * 50)

        self.assertEquals(self.scheduler.getNextChannel(), ch)

        def cb(lc):
            self.assertEquals(self.buffer.getvalue(),
                '\x00#\xb9r\x00\x002\x04\x08\x00\x00\x00' + ('f' * 50))

            self.assertEquals(self.encoder.buffer.getvalue(), '')

        self.encoder.start()

        return self.encoder.deferred.addCallback(cb)


class PacketWritingTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder.writePacket}
    """

    def test_uninitialisedChannel(self):
        """
        Test to confirm that writing a packet with an incomplete header raises
        L{codec.ChannelError}
        """
        channel = self.encoder.getChannel(0)
        header = channel.getHeader()

        self.assertEquals(header, None)

        e = self.assertRaises(codec.ChannelError, self.encoder.writePacket,
            0, '')
        self.assertTrue(str(e).startswith(
            'Tried to write a relative header to an initialised channel'))

    def test_inactiveWithQueue(self):
        """
        Test to ensure that C{RuntimeError} is raised if a packet is written
        to an inactive channel but the queue for that channel is not empty.
        """
        channel = self.encoder.getChannel(0)
        context = self.encoder.channelContext[channel]

        context.queue = ['foo']

        self.assertEquals(self.encoder.activeChannels, [])

        e = self.assertRaises(RuntimeError, self.encoder.writePacket,
            0, '', 0, 0, 0)
        self.assertEquals(str(e), 'Queue is not empty?')

    def test_noQueue(self):
        self.executed = False
        self.assertEquals(self.encoder.channels, {})
        self.assertEquals(self.encoder.activeChannels, [])
        self.assertEquals(self.encoder.channelContext, {})

        d = self.encoder.writePacket(0, 'foobar', 0, 0, 0)

        self.assertTrue(isinstance(d, defer.Deferred))
        self.assertTrue(d.called)

        def cb(r):
            self.assertEquals(r, None)
            channel = self.encoder.getChannel(0)
            context = self.encoder.channelContext[channel]

            self.assertEquals(self.encoder.activeChannels, [0])
            self.assertEquals(context.buffer.getvalue(), 'foobar')

            self.executed = True

        d.addCallback(cb)

        return d.addCallback(lambda _: self.assertTrue(self.executed))

    def test_active(self):
        channel = self.encoder.getChannel(0)
        context = self.encoder.channelContext[channel]

        context.currentPacket = 'foo'
        context.queue = ['foo']

        d = self.encoder.writePacket(0, 'foobar', 0, 0, 0)

        self.assertTrue(isinstance(d, defer.Deferred))
        self.assertFalse(d.called)

        self.assertEquals(len(context.queue), 2)

        n = context.queue[1]

        self.assertTrue(isinstance(n, tuple))
        self.assertEquals(len(n), 3)

        h, p, d2 = n

        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertEquals(h.channelId, 0)
        self.assertEquals(h.streamId, 0)
        self.assertEquals(h.datatype, 0)
        self.assertEquals(h.timestamp, 0)
        self.assertEquals(h.bodyLength, 6)

        self.assertEquals(p, 'foobar')
        self.assertIdentical(d, d2)


class FrameWritingTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder.writeFrame}
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.buffer = self.encoder.buffer
        self.contexts = self.encoder.channelContext
        self.encoder.frameSize = 128

    def _generateContext(self, bodyLength=1000):
        channel = self.encoder.createChannel(self._channelId)

        h = mocks.Header(relative=False, channelId=self._channelId,
            bodyLength=bodyLength)

        context = self.contexts[channel]

        context.reset(h)
        channel.setHeader(h)

        return context

    def test_nodata(self):
        context = self._generateContext()
        channel = context.channel

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(
            min(channel.bodyRemaining, self.encoder.frameSize), 128)
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

        channel.dataReceived('a' * 200)

        self.assertEquals(self.buffer.getvalue(), '')

        self.encoder.writeFrame(context)
        self.assertEquals(self.buffer.getvalue(), '\x00\x003C\x00\x03\xe8\x03'
            'F\x00\x00\x00' + ('a' * self.encoder.frameSize))

        self.buffer.truncate()

        self.assertEquals(context.buffer.getvalue(), 'a' * 72)
        self.assertTrue(0 in self.encoder.activeChannels)
        self.assertIdentical(context.header, header)
        self.assertEquals(context.getMinimumFrameSize(), 128)

        self.encoder.writeFrame(context)

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertFalse(0 in self.encoder.activeChannels)

        channel.dataReceived('b' * 56)

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertTrue(0 in self.encoder.activeChannels)

        self.encoder.writeFrame(context)

        self.assertEquals(self.buffer.getvalue(),
            '\xc0' + ('a' * 72) + ('b' * 56))


class EncodingTestCase(BaseEncoderTestCase):
    """
    General encoding test cases.
    """

    def test_noActiveChannels(self):
        """
        Test to ensure that a call to L{self.encoder.encode} when the call to
        scheduler.getNextChannel() returns C{None} pauses itself.
        """
        self.assertEquals(self.scheduler.getNextChannel(), None)

        self.encoder.start()

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertNotEquals(self.encoder.deferred, None)

        self.encoder.encode()

        self.assertEquals(self.encoder.deferred, None)
        self.assertEquals(self.buffer.getvalue(), '')


class ContextQueueTestCase(BaseEncoderTestCase):
    """
    Tests for ensuring queue integrity when dealing with packets and
        L{codec.ChannelContext}.
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = self.encoder.getChannel(0)
        self.context = self.encoder.channelContext[self.channel]
        self.buffer = self.context.buffer

    def test_callback(self):
        """
        Ensure that the currentPacket's callback is called when executing the
        L{runQueue}.
        """
        self.executed = False

        def cb(res):
            self.assertEquals(res, None)
            self.assertEquals(self.context.currentPacket, None)
            self.assertEquals(self.context.queue, [])

            self.executed = True

        d = self.context.currentPacket = defer.Deferred()

        self.assertEquals(self.context.queue, [])

        self.context.runQueue()

        d.addCallback(cb)

        return d.addCallback(lambda _: self.assertTrue(self.executed))

    def test_pop(self):
        """
        Ensure that the queue operates a FIFO policy
        """
        d1, d2 = defer.Deferred(), defer.Deferred()
        h1 = mocks.Header(relative=False, channelId=0, streamId=0, datatype=2,
            bodyLength=3, timestamp=0)
        h2 = mocks.Header(relative=False, channelId=0, streamId=8, datatype=6,
            bodyLength=4, timestamp=2000)

        self.context.queue = [(h1, 'foo', d1), (h2, 'spam', d2)]

        self.assertEquals(self.context.currentPacket, None)

        self.context.runQueue()

        self.assertEquals(self.context.queue, [(h2, 'spam', d2)])
        self.assertEquals(self.context.currentPacket, d1)

        self.assertIdentical(self.channel.getHeader(), h1)

        d1.callback(None), d2.callback(None)