# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp.codec}.
"""

from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy.tests.util import DummyChannelManager, DummyChannel, DummyHeader


class BaseDecoderTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.manager = DummyChannelManager()
        self.decoder = codec.Decoder(self.manager)
        self.buffer = self.decoder.buffer


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

    def test_getBytesAvailableForChannel(self):
        c = DummyChannel()
        c.setHeader(DummyHeader(bodyLength=1000, relative=False))

        self.assertEquals(self.buffer.remaining(), 0)
        self.assertEquals(c.frameRemaining, 128)
        self.assertEquals(c.bodyRemaining, 1000)
        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 0)

        self.buffer.write(' ' * 10)
        self.buffer.seek(0)
        c.write(' ' * 10)

        self.assertEquals(self.buffer.remaining(), 10)
        self.assertEquals(c.frameRemaining, 118)
        self.assertEquals(c.bodyRemaining, 990)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 10)

        self.buffer.write(' ' * (c.frameSize - 1))
        self.buffer.seek(0)
        c.write(' ' * (c.frameSize - 11))

        self.assertEquals(self.buffer.remaining(), 127)
        self.assertEquals(c.frameRemaining, 1)
        self.assertEquals(c.bodyRemaining, 873)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 1)

        self.buffer.write(' ' * c.frameSize)
        self.buffer.seek(0)
        c.write(' ')

        self.assertEquals(self.buffer.remaining(), 128)
        self.assertEquals(c.frameRemaining, 0)
        self.assertEquals(c.bodyRemaining, 872)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 0)

        c = DummyChannel()
        c.setHeader(DummyHeader(bodyLength=1000, relative=False))
        c.buffer = ' ' * 999

        self.buffer.truncate()
        self.buffer.write('a' * 10)
        self.buffer.seek(0)

        self.assertEquals(self.buffer.remaining(), 10)
        self.assertEquals(c.frameRemaining, 128)
        self.assertEquals(c.bodyRemaining, 1)

        self.assertEquals(self.decoder.getBytesAvailableForChannel(c), 1)

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

        self.assertEquals(self.buffer.tell(), 3)
        self.assertEquals(self.buffer.getvalue(), 'foo')
        self.assertEquals(self.decoder.currentChannel, None)
        self.assertFalse(job.running)


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
            self.assertTrue(isinstance(c, DummyChannel))
            self.assertEquals(c.frameRemaining, DummyChannel.frameSize)
            self.assertEquals(c.frames, 0)
            self.assertEquals(c.buffer, '')
            self.assertFalse(self.job.running)

            self.assertEquals(self.manager.channels, {21: c})

        return self.deferred.addCallback(cb)

    def test_partialBody(self):
        c = DummyChannel()
        c.setHeader(DummyHeader(bodyLength=1000, relative=False))
        self.decoder.currentChannel = c

        self.buffer.write('hello')
        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)

            self.assertEquals(c.frameRemaining, DummyChannel.frameSize - 5)
            self.assertEquals(c.frames, 0)
            self.assertEquals(c.buffer, 'hello')

        return self.deferred.addCallback(cb)

    def test_fullFrame(self):
        c = DummyChannel()
        c.setHeader(DummyHeader(bodyLength=1000, relative=False))

        self.decoder.currentChannel = c

        self.buffer.write(' ' * DummyChannel.frameSize)
        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)

            self.assertEquals(c.frameRemaining, DummyChannel.frameSize)
            self.assertEquals(c.frames, 1)
            self.assertEquals(c.buffer, ' ' * DummyChannel.frameSize)

        return self.deferred.addCallback(cb)

    def test_singleHeaderFullBody(self):
        # a full header channelId 3, datatype 2, bodyLength 50, streamId 1, timestamp 10
        self.buffer.write('\x03\x00\x00\n\x00\x002\x02\x00\x00\x00\x01')
        # complete the frame
        self.buffer.write('a' * 50)

        self.buffer.seek(0)

        def cb(lc):
            self.assertEquals(self.buffer.tell(), 0)
            self.assertEquals(self.buffer.getvalue(), '')
            self.assertFalse(self.job.running)

            c = self.manager.channels[3]
            h = c.header

            self.assertEquals(h.channelId, 3)
            self.assertEquals(h.datatype, 2)
            self.assertEquals(h.bodyLength, 50)
            self.assertEquals(h.streamId, 1)
            self.assertEquals(h.timestamp, 10)

            self.assertEquals(c.buffer, 'a' * 50)

            self.assertEquals(self.decoder.currentChannel, None)

        return self.deferred.addCallback(cb)

    def test_multipleHeaders2channels(self):
        # a full header channelId 3, datatype 2, bodyLength 500, streamId 1, timestamp 10
        self.buffer.write('\x03\x00\x00\n\x00\x01\xf4\x02\x00\x00\x00\x01')
        # complete the frame
        self.buffer.write('a' * DummyChannel.frameSize)
        # a full header channelId 5, datatype 5, bodyLength 500, streamId 1, timestamp 50
        self.buffer.write('\x05\x00\x002\x00\x01\xf4\x05\x00\x00\x00\x01')
        # complete the frame
        self.buffer.write('b' * DummyChannel.frameSize)
        # a relative header for channelId 3
        self.buffer.write('\xc3')
        # complete the frame
        self.buffer.write('c' * DummyChannel.frameSize)

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

            self.assertEquals(c.buffer, 'a' * DummyChannel.frameSize + 'c' * DummyChannel.frameSize)

            c = self.manager.channels[5]
            h = c.header

            self.assertEquals(h.channelId, 5)
            self.assertEquals(h.datatype, 5)
            self.assertEquals(h.bodyLength, 500)
            self.assertEquals(h.streamId, 1)
            self.assertEquals(h.timestamp, 50)

            self.assertEquals(c.buffer, 'b' * DummyChannel.frameSize)

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
        channel = self.decoder.currentChannel = DummyChannel()
        channel.setHeader(DummyHeader(bodyLength=1000, relative=False))

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

        self.decoder.readFrame()

        self.assertEquals(self.buffer.getvalue(), '')
        self.assertEquals(channel.buffer, '')
        self.assertEquals(channel.frames, 0)

    def test_partial(self):
        channel = self.decoder.currentChannel = DummyChannel()
        channel.setHeader(DummyHeader(bodyLength=1000, relative=False))

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
        channel.setHeader(DummyHeader(bodyLength=1000, relative=False))

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
        channel.setHeader(DummyHeader(bodyLength=1000, relative=False))

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
