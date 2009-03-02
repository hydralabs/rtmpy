# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp.codec}.
"""

from twisted.internet import reactor, defer, task
from twisted.trial import unittest
from zope.interface import implements

from rtmpy.rtmp import codec, interfaces
from rtmpy import util


class DummyChannelManager(object):
    """
    """

    implements(interfaces.IChannelManager)


class DummyChannel(object):
    """
    """

    implements(interfaces.IChannel)

    frameSize = 128

    def __init__(self):
        self.frameRemaining = self.frameSize
        self.frames = 0
        self.buffer = ''

    def write(self, data):
        self.buffer += str(data)

        l = len(data)

        if l < self.frameSize:
            self.frameRemaining -= l

            return

        while l >= self.frameSize:
            self.frames += 1
            l -= self.frameSize

        if self.frameRemaining != self.frameSize and l + self.frameRemaining >= self.frameSize:
            self.frames += 1
            l -= self.frameSize

        if l > 0:
            self.frameRemaining = l
        else:
            self.frameRemaining = self.frameSize


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
        d = DummyChannelManager()
        c = codec.BaseCodec(d)

        self.assertRaises(NotImplementedError, self._getJob, c)

    def test_init(self):
        e = self.assertRaises(TypeError, codec.BaseCodec, 'hello')
        self.assertEquals(str(e), "IChannelManager expected (got <type 'str'>)")

        obj = object()

        codec.BaseCodec.getJob = lambda self: obj

        d = DummyChannelManager()
        self.assertTrue(interfaces.IChannelManager.providedBy(d))
        c = codec.BaseCodec(d)

        self.assertIdentical(c.manager, d)
        self.assertEquals(c.deferred, None)
        self.assertTrue(isinstance(c.buffer, util.BufferedByteStream))
        self.assertTrue(isinstance(c.job, task.LoopingCall))

    def test_destroy_not_running(self):
        d = DummyChannelManager()
        c = codec.BaseCodec(d)

        self.assertFalse(c.job.running)

        c.__del__()

    def test_destroy_running(self):
        self.executed = False
        d = DummyChannelManager()
        c = codec.BaseCodec(d)

        def cb(lc):
            self.assertIdentical(c.job, lc)
            self.executed = True

        c.start().addCallback(cb)

        self.assertFalse(self.executed)
        c.__del__()
        self.assertTrue(self.executed)

    def test_start(self):
        d = DummyChannelManager()
        c = codec.BaseCodec(d)

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
        d = DummyChannelManager()
        c = codec.BaseCodec(d)
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


class BaseDecoderTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.manager = DummyChannelManager()
        self.decoder = codec.Decoder(self.manager)
        self.buffer = self.decoder.buffer


class DecoderTestCase(BaseDecoderTestCase):
    """
    Tests for L{codec.Decoder}
    """

    def test_job(self):
        self.assertEquals(self.decoder.getJob(), self.decoder.decode)

    def test_init(self):
        self.assertEquals(self.decoder.currentChannel, None)

    def test_dataReceived(self):
        self.assertEquals(self.buffer.getvalue(), '')

        self.decoder.dataReceived('hello')
        self.assertEquals(self.buffer.getvalue(), 'hello')

        # seek to the beginning of the stream
        self.buffer.seek(0)

        self.decoder.dataReceived('hi')
        self.assertEquals(self.buffer.getvalue(), 'hellohi')

    def test_readHeader(self):
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(self.decoder.readHeader(), None)

        # this is a valid 8 byte header
        full_header = 'U\x03\x92\xfa\x00z\n\x03'

        self.buffer.write(full_header[:5])
        self.buffer.seek(0)
        self.assertEquals(self.decoder.readHeader(), None)
        self.assertEquals(self.buffer.tell(), 0)

        self.buffer.seek(2)
        self.assertEquals(self.buffer.tell(), 2)
        self.assertEquals(self.decoder.readHeader(), None)
        self.assertEquals(self.buffer.tell(), 2)

        self.buffer.seek(0, 2)
        self.buffer.write(full_header[5:])
        self.assertEquals(self.buffer.getvalue(), full_header)
        self.buffer.seek(0)

        h = self.decoder.readHeader()
        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertEquals(self.buffer.tell(), len(full_header))

    def test_canContinue(self):
        self.executed = False

        def cb(lc):
            self.executed = True

        job = self.decoder.job
        self.decoder.start().addCallback(cb)

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertFalse(self.decoder.canContinue())
        self.assertTrue(self.executed)
        self.assertEquals(job.running, False)

        self.executed = False

        self.decoder.start().addCallback(cb)

        self.buffer.write('1234')
        self.buffer.seek(0)
        self.assertEquals(self.buffer.remaining(), 4)

        self.assertTrue(self.decoder.canContinue(3))
        self.assertTrue(self.executed)
        self.assertTrue(self.decoder.canContinue(4))
        self.assertFalse(self.decoder.canContinue(5))

    def test_getBytesAvailableForChannel(self):
        c = DummyChannel()

        self.assertEquals(self.buffer.remaining(), 0)
        self.assertEquals(c.frameRemaining, 128)
        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 0)

        self.buffer.write(' ' * 10)
        self.buffer.seek(0)
        c.write(' ' * 10)

        self.assertEquals(self.buffer.remaining(), 10)
        self.assertEquals(c.frameRemaining, 118)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 10)

        self.buffer.write(' ' * (c.frameSize - 1))
        self.buffer.seek(0)
        c.write(' ' * (c.frameSize - 11))

        self.assertEquals(self.buffer.remaining(), 127)
        self.assertEquals(c.frameRemaining, 1)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 1)

        self.buffer.write(' ' * c.frameSize)
        self.buffer.seek(0)
        c.write(' ')

        self.assertEquals(self.buffer.remaining(), 128)
        self.assertEquals(c.frameRemaining, 0)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 0)

    def test_noop(self):
        """
        If the decoder can't continue then the buffer should be left untouched
        """
        self.buffer.write('foo')
        self.buffer.seek(3)
        self.assertEquals(self.buffer.tell(), 3)
        self.assertFalse(self.decoder.canContinue())

        self.decoder.decode()

        self.assertEquals(self.buffer.tell(), 3)


class FrameReadingTestCase(BaseDecoderTestCase):
    """
    Tests for L{codec.Decoder.readFrame}
    """

    def test_nochannel(self):
        self.assertEquals(self.decoder.currentChannel, None)

        e = self.assertRaises(codec.DecodeError, self.decoder.readFrame)
        self.assertEquals(str(e), 'Channel is required to read frame')

    def test_notavailable(self):
        channel = self.decoder.currentChannel = DummyChannel()
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

    def test_partial(self):
        channel = self.decoder.currentChannel = DummyChannel()

        self.buffer.write('foo.bar.baz')
        self.buffer.seek(0)

        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), 11)
        self.assertEquals(channel.buffer, 'foo.bar.baz')
        self.assertEquals(channel.frames, 0)

    def test_full(self):
        channel = self.decoder.currentChannel = DummyChannel()

        self.assertEquals(channel.frameRemaining, channel.frameSize)

        self.buffer.write(' ' * channel.frameSize)
        self.buffer.seek(0)

        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), channel.frameSize)
        self.assertEquals(channel.buffer, ' ' * channel.frameSize)
        self.assertEquals(channel.frames, 1)
        self.assertEquals(self.decoder.currentChannel, None)

    def test_moreThanOne(self):
        channel = self.decoder.currentChannel = DummyChannel()

        self.assertEquals(channel.frameRemaining, channel.frameSize)

        self.buffer.write(' ' * (channel.frameSize + 50))
        self.buffer.seek(0)

        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), channel.frameSize)
        self.assertEquals(channel.buffer, ' ' * channel.frameSize)
        self.assertEquals(channel.frames, 1)
        self.assertEquals(channel.frameRemaining, 128)
        self.assertEquals(self.decoder.currentChannel, None)

        self.decoder.currentChannel = channel
        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), channel.frameSize + 50)
        self.assertEquals(channel.buffer, ' ' * (channel.frameSize + 50))
        self.assertEquals(channel.frames, 1)
        self.assertEquals(channel.frameRemaining, 78)
        self.assertEquals(self.decoder.currentChannel, channel)
