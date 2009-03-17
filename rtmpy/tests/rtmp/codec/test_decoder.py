# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.codec}.
"""

from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy.tests.rtmp import mocks


class BaseDecoderTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.manager = mocks.ChannelManager()
        self.decoder = codec.Decoder(self.manager)
        self.buffer = self.decoder.buffer

    def _generateChannel(self, header=None):
        c = mocks.Channel()
        c.registerManager(self.manager)

        c.reset()

        if header is not None:
            c.setHeader(header)

        return c


class DecoderClassTestCase(BaseDecoderTestCase):
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
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertFalse(self.decoder.canContinue())

        self.buffer.write('1234')
        self.buffer.seek(0)
        self.assertEquals(self.buffer.remaining(), 4)
        self.assertTrue(self.decoder.canContinue(3))
        self.assertTrue(self.decoder.canContinue(4))
        self.assertFalse(self.decoder.canContinue(5))

        def cb(lc):
            job = self.decoder.job
            self.assertEquals(job.running, False)

        return self.decoder.start().addCallback(cb)

    def test_noop(self):
        """
        If the decoder can't continue then the buffer should be left untouched
        """
        self.decoder.start()

        job = self.decoder.job

        self.assertTrue(job.running)
        self.buffer.write('foo')
        self.buffer.seek(3)
        self.assertEquals(self.buffer.tell(), 3)
        self.assertFalse(self.decoder.canContinue())
        self.assertEquals(self.decoder.currentChannel, None)

        self.decoder.decode()

        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(self.buffer.getvalue(), 'foo')
        self.assertEquals(self.decoder.currentChannel, None)
        self.assertFalse(job.running)


class GetBytesAvailableForChannelTestCase(BaseDecoderTestCase):
    """
    Tests for L{codec.Decoder.getBytesAvailableForChannel}.
    """

    def setUp(self):
        BaseDecoderTestCase.setUp(self)

        self.channel = self._generateChannel(
            mocks.Header(bodyLength=1000, relative=False))

    def gba(self):
        return self.decoder.getBytesAvailableForChannel(self.channel)

    def test_noop(self):
        self.assertEquals(self.buffer.remaining(), 0)
        self.assertEquals(self.channel.bodyRemaining, 1000)
        self.assertEquals(self.gba(), 0)

    def test_partialBodyPartialFrame(self):
        self.buffer.write(' ' * 10)
        self.buffer.seek(0)
        self.channel.write(' ' * 10)

        self.assertEquals(self.buffer.remaining(), 10)
        self.assertEquals(self.manager.frameSize, 128)
        self.assertEquals(self.channel.bodyRemaining, 990)

        self.assertEquals(self.gba(), 10)

    def test_partialBodyNearlyFullFrame(self):
        self.buffer.write(' ' * (self.manager.frameSize - 1))
        self.buffer.seek(0)
        self.channel.write(' ' * (self.manager.frameSize - 11))

        self.assertEquals(self.buffer.remaining(), 127)
        self.assertEquals(self.manager.frameSize, 128)
        self.assertEquals(self.channel.bodyRemaining, 883)

        self.assertEquals(self.gba(), 127)

    def test_partialBodyFullFrame(self):
        self.buffer.write(' ' * self.manager.frameSize)
        self.buffer.seek(0)
        self.channel.write(' ')

        self.assertEquals(self.buffer.remaining(), 128)
        self.assertEquals(self.manager.frameSize, 128)
        self.assertEquals(self.channel.bodyRemaining, 999)

        self.assertEquals(self.gba(), 128)

    def test_nearlyFullBodyPartialFrame(self):
        self.channel.write(' ' * 999)

        self.buffer.truncate()
        self.buffer.write('a' * 10)
        self.buffer.seek(0)

        self.assertEquals(self.buffer.remaining(), 10)
        self.assertEquals(self.manager.frameSize, 128)
        self.assertEquals(self.channel.bodyRemaining, 1)

        self.assertEquals(self.gba(), 1)


class DecodingTestCase(BaseDecoderTestCase):
    """
    Tests for decoding rather than functional test cases
    """

    def _cb(self, *args):
        self.assertFalse(self.job.running)

    def setUp(self):
        BaseDecoderTestCase.setUp(self)

        self.decoder.start()
        self.deferred = self.decoder.deferred
        self.job = self.decoder.job

        self.deferred.addCallback(self._cb)

    def test_noop(self):
        self.assertEquals(self.buffer.getvalue(), '')
        self.assertTrue(self.job.running)
        self.assertEquals(self.decoder.currentChannel, None)

        def cb(lc):
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertEquals(self.decoder.currentChannel, None)
            self.assertFalse(self.job.running)

        return self.deferred.addCallback(cb)

    def test_incompleteHeader(self):
        # this is a valid 8 byte header
        full_header = 'U\x03\x92\xfa\x00z\n\x03'
        self.buffer.write(full_header[:5])
        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), 'U\x03\x92\xfa\x00')
            self.assertEquals(self.decoder.currentChannel, None)
            self.assertFalse(self.job.running)

        return self.deferred.addCallback(cb)

    def test_fullHeaderNoBody(self):
        # this is a valid 12 byte header
        full_header = '\x15\x03\x92\xfa\x00z\n\x03\x00\x00\x00-'
        self.buffer.write(full_header)
        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')

            c = self.decoder.currentChannel
            self.assertTrue(isinstance(c, mocks.Channel))
            self.assertEquals(c.frames, 0)
            self.assertEquals(c.buffer, '')
            self.assertFalse(self.job.running)

            self.assertEquals(self.manager.channels, {21: c})

        return self.deferred.addCallback(cb)

    def test_partialBody(self):
        c = self._generateChannel(mocks.Header(bodyLength=1000, relative=False))

        self.decoder.currentChannel = c

        self.buffer.write('hello')
        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)

            self.assertEquals(c.frames, 0)
            self.assertEquals(c.buffer, 'hello')

        return self.deferred.addCallback(cb)

    def test_fullFrame(self):
        c = self._generateChannel(mocks.Header(channelId=3, bodyLength=1000,
            relative=False))

        self.decoder.currentChannel = c

        self.buffer.write(' ' * self.manager.frameSize)
        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)

            self.assertEquals(c.frames, 1)
            self.assertEquals(c.buffer, ' ' * self.manager.frameSize)

        return self.deferred.addCallback(cb)

    def test_singleHeaderFullBody(self):
        # a full header channelId 3, datatype 2, bodyLength 50, streamId 1, timestamp 10
        self.buffer.write('\x03\x00\x00\n\x00\x002\x02\x01\x00\x00\x00')
        # complete the frame
        self.buffer.write('a' * 50)

        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)

            c = self.manager.channels[3]
            h = c.getHeader()

            self.assertEquals(h.channelId, 3)
            self.assertEquals(h.datatype, 2)
            self.assertEquals(h.bodyLength, 50)
            self.assertEquals(h.streamId, 1)
            self.assertEquals(h.timestamp, 10)

            self.assertEquals(self.manager.complete, [(3, 'a' * 50)])

            self.assertEquals(c.buffer, 'a' * 50)

            self.assertEquals(self.decoder.currentChannel, None)

        return self.deferred.addCallback(cb)

    def test_multipleHeaders2channels(self):
        # a full header channelId 3, datatype 2, bodyLength 500, streamId 1, timestamp 10
        self.buffer.write('\x03\x00\x00\n\x00\x01\xf4\x02\x01\x00\x00\x00')
        # complete the frame
        self.buffer.write('a' * self.manager.frameSize)
        # a full header channelId 5, datatype 5, bodyLength 500, streamId 1, timestamp 50
        self.buffer.write('\x05\x00\x002\x00\x01\xf4\x05\x01\x00\x00\x00')
        # complete the frame
        self.buffer.write('b' * self.manager.frameSize)
        # a relative header for channelId 3
        self.buffer.write('\xc3')
        # complete the frame
        self.buffer.write('c' * self.manager.frameSize)

        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)
            self.assertEquals(self.manager.channels.keys(), [3, 5])

            c = self.manager.channels[3]
            h = c.header

            self.assertEquals(h.channelId, 3)
            self.assertEquals(h.datatype, 2)
            self.assertEquals(h.bodyLength, 500)
            self.assertEquals(h.streamId, 1)
            self.assertEquals(h.timestamp, 10)

            self.assertEquals(c.buffer, 'a' * self.manager.frameSize + \
                'c' * self.manager.frameSize)

            c = self.manager.channels[5]
            h = c.header

            self.assertEquals(h.channelId, 5)
            self.assertEquals(h.datatype, 5)
            self.assertEquals(h.bodyLength, 500)
            self.assertEquals(h.streamId, 1)
            self.assertEquals(h.timestamp, 50)

            self.assertEquals(c.buffer, 'b' * self.manager.frameSize)

            self.assertEquals(self.decoder.currentChannel, None)

        return self.deferred.addCallback(cb)

class FrameReadingTestCase(BaseDecoderTestCase):
    """
    Tests for L{codec.Decoder.readFrame}
    """

    def test_nochannel(self):
        self.assertEquals(self.decoder.currentChannel, None)

        e = self.assertRaises(codec.DecodeError, self.decoder.readFrame)
        self.assertEquals(str(e), 'Channel is required to read frame')

    def test_notavailable(self):
        channel = self.decoder.currentChannel = self._generateChannel(
            mocks.Header(bodyLength=1000, relative=False))

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

    def test_partial(self):
        channel = self.decoder.currentChannel = self._generateChannel(
            mocks.Header(bodyLength=1000, relative=False))

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
        channel = self.decoder.currentChannel = self._generateChannel(
            mocks.Header(bodyLength=1000, relative=False))

        self.buffer.write(' ' * self.manager.frameSize)
        self.buffer.seek(0)

        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), self.manager.frameSize)
        self.assertEquals(channel.buffer, ' ' * self.manager.frameSize)
        self.assertEquals(channel.frames, 1)
        self.assertEquals(self.decoder.currentChannel, None)

    def test_moreThanOne(self):
        channel = self.decoder.currentChannel = self._generateChannel(
            mocks.Header(bodyLength=1000, relative=False))

        self.buffer.write(' ' * (self.manager.frameSize + 50))
        self.buffer.seek(0)

        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), self.manager.frameSize)
        self.assertEquals(channel.buffer, ' ' * self.manager.frameSize)
        self.assertEquals(channel.frames, 1)
        self.assertEquals(self.decoder.currentChannel, None)

        self.decoder.currentChannel = channel
        self.decoder.readFrame()

        self.assertEquals(self.buffer.tell(), self.manager.frameSize + 50)
        self.assertEquals(channel.buffer, ' ' * (self.manager.frameSize + 50))
        self.assertEquals(channel.frames, 1)
        self.assertEquals(self.decoder.currentChannel, channel)
