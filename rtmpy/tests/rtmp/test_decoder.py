# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
Decoding tests for L{rtmpy.rtmp.codec}.
"""

import unittest

from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import codec, header


class MockChannel(object):
    """
    Pretend to be a channel
    """

    def setFrameSize(self, size):
        self.frameSize = size


class ChannelMeta(object):
    """
    Implements L{codec.IChannelMeta}
    """

    datatype = None
    channelId = None
    timestamp = None
    streamId = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class MockFrameReader(object):
    """
    Pretend to act like a L{codec.FrameReader}
    """

    @classmethod
    def __init__(cls, self, stream=None, bytesInterval=None):
        self.stream = stream
        self.bytesInterval = bytesInterval
        self.bytes = 0
        self._nextInterval = bytesInterval

    @classmethod
    def next(cls, self):
        return self.events.pop(0)


class MockChannelDemuxer(MockFrameReader):
    """
    Pretend to act like a L{codec.ChannelDemuxer}
    """


class MockStreamFactory(object):
    def __init__(self, test):
        self.test = test

    def getStream(self, *args):
        return self.test.getStream(*args)


class DispatchTester(object):
    """
    """

    def __init__(self, test):
        self.test = test
        self.messages = []
        self.intervals = []

    def dispatchMessage(self, *args):
        fod = getattr(self.test, 'failOnDispatch', False)

        if fod:
            raise AssertionError('Message dispatched %r' % (args,))

        self.messages.append(args)

    def bytesInterval(self, bytes):
        self.intervals.append(bytes)


class MockStream(object):
    """
    """

    timestamp = 0


class FrameReaderTestCase(unittest.TestCase):
    """
    Tests for L{codec.FrameReader}
    """

    def setUp(self):
        self.reader = codec.FrameReader()
        self.channels = self.reader.channels
        self.stream = self.reader.stream

    def test_init(self):
        self.assertEqual(self.reader.frameSize, 128)
        self.assertEqual(self.reader.channels, {})
        self.assertEqual(self.reader.stream.getvalue(), '')

    def test_set_frame_size(self):
        self.reader.setFrameSize(500)

        self.assertEqual(self.reader.frameSize, 500)

    def test_channel_frame_size(self):
        c = self.channels[1] = MockChannel()

        self.reader.setFrameSize(500)

        self.assertEqual(c.frameSize, 500)

    def test_reset(self):
        full = header.Header(3, datatype=2, bodyLength=2, streamId=1, timestamp=10)

        header.encode(self.stream, full)
        self.stream.write('a' * 2)

        self.stream.seek(0)

        self.reader.next()
        channel = self.channels[3]

        self.assertEqual(channel.bytes, 0)

    def test_send(self):
        self.assertEqual(self.stream.getvalue(), '')

        self.reader.send('foo')

        self.assertEqual(self.stream.getvalue(), 'foo')

    def test_eof(self):
        self.assertTrue(self.stream.at_eof())
        self.assertRaises(StopIteration, self.reader.next)

    def test_ioerror_seek(self):
        self.stream.append('foo')
        self.stream.seek(1)

        self.assertEqual(self.stream.tell(), 1)
        self.assertRaises(StopIteration, self.reader.next)

        self.assertEqual(self.stream.tell(), 1)

    def test_simple(self):
        """
        Do a sanity check for a simple 4 frame 1 channel rtmp stream.
        """
        def check_meta(meta, timestamp=10):
            self.assertEqual(meta.channelId, 3)
            self.assertEqual(meta.streamId, 1)
            self.assertEqual(meta.datatype, 2)
            self.assertEqual(meta.bodyLength, 500)
            self.assertEqual(meta.timestamp, timestamp)

        size = self.reader.frameSize

        full = header.Header(3, datatype=2, bodyLength=500, streamId=1, timestamp=10)

        header.encode(self.stream, full)
        self.stream.write('a' * size)

        header.encode(self.stream, full, full)
        self.stream.write('b' * size)

        header.encode(self.stream, full, full)
        self.stream.write('c' * size)

        header.encode(self.stream, full, full)
        self.stream.write('d' * (size - 12))

        self.stream.seek(0)
        bytes, complete, meta = self.reader.next()

        self.assertEqual(bytes, 'a' * self.reader.frameSize)
        self.assertFalse(complete)
        check_meta(meta)

        bytes, complete, meta = self.reader.next()

        self.assertEqual(bytes, 'b' * self.reader.frameSize)
        self.assertFalse(complete)
        check_meta(meta, 10)

        bytes, complete, meta = self.reader.next()

        self.assertEqual(bytes, 'c' * self.reader.frameSize)
        self.assertFalse(complete)
        check_meta(meta, 10)

        bytes, complete, meta = self.reader.next()

        self.assertEqual(bytes, 'd' * (size - 12))
        self.assertTrue(complete)
        check_meta(meta, 10)

        self.assertRaises(StopIteration, self.reader.next)

    def test_iter(self):
        self.assertIdentical(iter(self.reader), self.reader)

        h = header.Header(2, bodyLength=0, datatype=0, timestamp=0, streamId=0)
        header.encode(self.stream, h)

        self.stream.seek(0)

        self.assertNotEqual([x for x in self.reader], [])
        self.assertTrue(self.stream.at_eof)

    def test_reassign(self):
        """
        Ensure that when a channel is complete it can be repurposed via a relative
        header.
        """
        full_header = header.Header(52, datatype=2, timestamp=55,
            bodyLength=256, streamId=4)

        # only change the bodyLength and timestamp
        relative_header = header.Header(52, datatype=2, streamId=4,
            bodyLength=256, timestamp=45)

        header.encode(self.stream, full_header)
        self.stream.write('a' * self.reader.frameSize)
        header.encode(self.stream, relative_header, full_header)
        self.stream.write('b' * self.reader.frameSize)

        self.stream.seek(0)

        bytes, complete, meta = self.reader.next()

        self.assertEqual(bytes, 'a' * 128)
        self.assertFalse(complete)
        self.assertEqual(meta.timestamp, 55)

        bytes, complete, meta = self.reader.next()

        self.assertEqual(bytes, 'b' * 128)
        self.assertTrue(complete)
        self.assertEqual(meta.timestamp, 100)


class DeMuxerTestCase(unittest.TestCase):
    """
    Tests for L{codec.DeMuxer}
    """

    def setUp(self):
        self.patch('codec.FrameReader', MockFrameReader)

        self.demuxer = codec.ChannelDemuxer()

    def add_events(self, *events):
        if not hasattr(self.demuxer, 'events'):
            self.demuxer.events = []

        self.demuxer.events.extend(events)

    def test_create(self):
        self.assertEqual(self.demuxer.bucket, {})

    def test_iterate(self):
        meta = ChannelMeta(channelId=1)

        self.add_events(
            ('foo', False, meta), ('bar', False, meta), ('baz', True, meta))

        self.assertEqual(self.demuxer.next(), (None, None))
        self.assertEqual(self.demuxer.bucket, {1: 'foo'})

        self.assertEqual(self.demuxer.next(), (None, None))
        self.assertEqual(self.demuxer.bucket, {1: 'foobar'})

        self.assertEqual(self.demuxer.next(), ('foobarbaz', meta))
        self.assertEqual(self.demuxer.bucket, {})

    def test_iter(self):
        self.assertIdentical(iter(self.demuxer), self.demuxer)


class DecoderTestCase(unittest.TestCase):
    """
    Tests for L{codec.Decoder}
    """

    def setUp(self):
        self.patch('codec.ChannelDemuxer', MockChannelDemuxer)

        self.dispatcher = DispatchTester(self)
        self.stream_factory = MockStreamFactory(self)
        self.decoder = codec.Decoder(self.dispatcher, self.stream_factory,
            stream=BufferedByteStream(), bytesInterval=codec.BYTES_INTERVAL)

        self.expected_streams = None
        self.streams = {}

    def add_events(self, *events):
        if not hasattr(self.decoder, 'events'):
            self.decoder.events = []

        self.decoder.events.extend(events)

    def getStream(self, streamId):
        if self.expected_streams:
            expected = self.expected_streams.pop(0)

            self.assertEqual(expected, streamId)

        try:
            return self.streams[streamId]
        except KeyError:
            s = self.streams[streamId] = MockStream()

            return s

    def test_create(self):
        self.assertIdentical(self.decoder.stream_factory, self.stream_factory)
        self.assertIdentical(self.decoder.dispatcher, self.dispatcher)

    def test_fail_on_dispatch(self):
        m = ChannelMeta(streamId=2, timestamp=0)
        self.add_events(('foo', m))
        self.expected_streams = [2]

        self.failOnDispatch = True

        self.assertRaises(AssertionError, self.decoder.next)

    def test_do_nothing(self):
        self.add_events((None, ChannelMeta(timestamp=0)))
        self.failOnDispatch = True

        self.assertEqual(self.decoder.next(), None)

    def test_simple(self):
        meta = ChannelMeta(streamId=2, timestamp=3, datatype='bar')

        self.add_events(('foo', meta))

        self.assertEqual(self.decoder.next(), None)
        self.assertEquals(len(self.dispatcher.messages), 1)

        stream, datatype, timestamp, data = self.dispatcher.messages[0]

        self.assertIdentical(stream, self.streams[2])
        self.assertEqual(datatype, 'bar')
        self.assertEqual(timestamp, 3)
        self.assertEqual(data, 'foo')

    def test_incrementing_timestamp(self):
        t1 = ChannelMeta(streamId=2, timestamp=2)
        t2 = ChannelMeta(streamId=2, timestamp=3)

        self.add_events(('foo', t1), ('foo', t2))

        self.assertEqual(self.decoder.next(), None)
        self.assertEqual(self.decoder.next(), None)

        self.assertEqual(t1.timestamp, 2)
        self.assertEqual(t2.timestamp, 3)


class BytesIntervalTestCase(unittest.TestCase):
    """
    Tests to ensure that the dispatcher receives the correct notification
    when a specified number of bytes has been read.
    """

    def setUp(self):
        self.dispatcher = DispatchTester(self)
        self.stream_factory = MockStreamFactory(self)
        self.decoder = codec.Decoder(self.dispatcher, self.stream_factory)

    def getStream(self, streamId):
        return MockStream()

    def test_interval(self):
        self.assertEqual(self.decoder.bytes, 0)
        self.decoder.setBytesInterval(8)

        self.decoder.send('\x03\x00\x00\x00\x00\x00\x00\r\x00\x00\x00\x00')

        self.decoder.next()
        self.assertEqual(self.decoder.bytes, 12)
        self.assertEqual(self.dispatcher.intervals, [12])

