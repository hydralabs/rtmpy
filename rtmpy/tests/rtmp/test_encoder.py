# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
Encoding tests for L{rtmpy.protocol.rtmp.codec}.
"""

import unittest

from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import codec, message


class MockDispatcher(object):
    """
    """

    def __init__(self):
        self.intervals = []

    def bytesInterval(self, bytes):
        self.intervals.append(bytes)


class BaseTestCase(unittest.TestCase):
    """
    Base functionality for other unit tests.
    """

    def setUp(self):
        self.output = BufferedByteStream()
        self.dispatcher = MockDispatcher()
        self.encoder = codec.Encoder(self.output, self.dispatcher)


class EncoderTestCase(BaseTestCase):
    """
    Tests for basic RTMP encoding.
    """

    def test_emtpy(self):
        self.assertRaises(StopIteration, self.encoder.next)

    def test_full(self):
        """
        Ensure that messages are queued when all channels are busy
        """
        self.encoder.channelsInUse = 0xffff
        while not self.encoder.isFull():
            self.encoder.send('foo', 8, 6, 0)

        self.encoder.send('bar', 12, 2, 3)

        self.assertEqual(self.encoder.pending, [('bar', 12, 2, 3, None)])

        self.encoder.next()

        self.assertEqual(self.encoder.pending, [('bar', 12, 2, 3, None)])

        self.encoder.next()

        self.assertEqual(self.encoder.pending, [])

    def test_interval(self):
        self.assertEqual(self.encoder.bytes, 0)
        self.encoder.setBytesInterval(8)

        self.encoder.send('bar', 12, 2, 3)
        self.encoder.next()

        self.assertEqual(self.dispatcher.intervals, [15])


class AquireChannelTestCase(BaseTestCase):
    """
    Tests for L{codec.Encoder.aquireChannel}
    """

    def test_simple(self):
        self.assertEqual(self.encoder.channelsInUse, 0)

        c = self.encoder.aquireChannel()

        self.assertTrue(isinstance(c, codec.ProducingChannel))

        self.assertEqual(c.channelId, 3)
        self.assertEqual(c.header, None)

        self.assertEqual(self.encoder.channelsInUse, 1)

    def test_overflow(self):
        """
        Attempt to aquire 62 channels
        """

        for i in xrange(codec.MIN_CHANNEL_ID, codec.MAX_CHANNELS):
            self.assertNotEqual(self.encoder.aquireChannel(), None)

        self.assertEqual(self.encoder.channelsInUse, 65596)
        self.assertEqual(self.encoder.aquireChannel(), None)


class ReleaseChannelTestCase(BaseTestCase):
    """
    Tests for L{codec.Encoder.releaseChannel}
    """

    def test_not_aquired(self):
        self.assertRaises(codec.EncodeError, self.encoder.releaseChannel, 3)

    def test_aquired(self):
        c = self.encoder.aquireChannel()

        self.assertEqual(self.encoder.channelsInUse, 1)

        self.encoder.releaseChannel(c.channelId)

        self.assertEqual(self.encoder.channelsInUse, 0)


class WritingTestCase(BaseTestCase):
    """
    Tests for writing RTMP frames.
    """

    def test_less_than_frame(self):
        self.encoder.send('foobar', 10, 1, 0)

        self.encoder.next()

        self.assertEqual(self.output.getvalue(),
            '\x03\x00\x00\x00\x00\x00\x06\n\x01\x00\x00\x00foobar')

        self.assertRaises(StopIteration, self.encoder.next)

    def test_multiple_frames(self):
        # 3 and a bit frames at 128 bytes per frame
        self.encoder.send('a' * (128 * 3 + 50), 10, 1, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x01\xb2\n\x01\x00\x00\x00')
        self.assertEqual(self.output.read(), 'a' * 128)
        self.assertTrue(self.output.at_eof())

        self.output.consume()

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(1), '\xc3')
        self.assertEqual(self.output.read(), 'a' * 128)
        self.assertTrue(self.output.at_eof())

        self.output.consume()

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(1), '\xc3')
        self.assertEqual(self.output.read(), 'a' * 128)
        self.assertTrue(self.output.at_eof())

        self.output.consume()

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(1), '\xc3')
        self.assertEqual(self.output.read(), 'a' * 50)
        self.assertTrue(self.output.at_eof())

        self.assertRaises(StopIteration, self.encoder.next)

    def test_interleave(self):
        # dispatch two messages
        self.encoder.send('a' * (128 + 1), 15, 7, 0)
        self.encoder.send('b' * (128 + 50), 8, 0xfffe, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x81\x0f\x07\x00\x00\x00')
        self.assertEqual(self.output.read(128), 'a' * 128)
        self.assertEqual(self.output.read(12),
            '\x04\x00\x00\x00\x00\x00\xb2\x08\xfe\xff\x00\x00')
        self.assertEqual(self.output.read(128), 'b' * 128)
        self.assertTrue(self.output.at_eof())
        self.output.consume()

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(1), '\xc3')
        self.assertEqual(self.output.read(1), 'a')
        self.assertEqual(self.output.read(1), '\xc4')
        self.assertEqual(self.output.read(50), 'b' * 50)
        self.assertTrue(self.output.at_eof())

    def test_reappropriate_channel(self):
        self.encoder.send('a' * 2, 8, 5, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x02\x08\x05\x00\x00\x00')
        self.assertEqual(self.output.read(2), 'a' * 2)

        self.assertTrue(self.output.at_eof())
        self.output.consume()

        self.encoder.send('b' * 2, 9, 7, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x02\x09\x07\x00\x00\x00')
        self.assertEqual(self.output.read(2), 'b' * 2)

        self.assertTrue(self.output.at_eof())


class TimestampTestCase(BaseTestCase):
    """
    Tests to check for relative or absolute timestamps are encoded properly
    """

    def test_simple(self):
        # data, datatype, timestamp
        self.encoder.send('', 13, 0, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x00\r\x00\x00\x00\x00')

        self.output.truncate()
        self.encoder.send('', 7, 0, 15)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(), '\x43\x00\x00\x0f\x00\x00\x00\x07')
        self.output.truncate()

        self.encoder.send('', 7, 0, 15)
        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(), '\x83\x00\x00\x00')
        self.output.truncate()


class CommandTypeTestCase(BaseTestCase):
    """
    Tests for encoding command types. These types should only be encoded on
    channel id of 2.

    @see: L{message.is_command_type}
    @note: The lack of C{next} calls in the tests. The control messages are
        immediately encoded.
    """

    def test_framesize(self):
        self.assertEqual(self.output.getvalue(), '')
        self.encoder.send('foo', message.FRAME_SIZE, 0, 10)
        self.assertEqual(self.output.getvalue(),
            '\x02\x00\x00\n\x00\x00\x03\x01\x00\x00\x00\x00foo')

    def test_bytes_read(self):
        self.assertEqual(self.output.getvalue(), '')
        self.encoder.send('bar', message.BYTES_READ, 0, 8)
        self.assertEqual(self.output.getvalue(),
            '\x02\x00\x00\x08\x00\x00\x03\x03\x00\x00\x00\x00bar')

    def test_control(self):
        self.assertEqual(self.output.getvalue(), '')
        self.encoder.send('spam', message.CONTROL, 0, 432)
        self.assertEqual(self.output.getvalue(),
            '\x02\x00\x01\xb0\x00\x00\x04\x04\x00\x00\x00\x00spam')

    def test_dsbw(self):
        self.assertEqual(self.output.getvalue(), '')
        self.encoder.send('eggs', message.DOWNSTREAM_BANDWIDTH, 0, 21)
        self.assertEqual(self.output.getvalue(),
            '\x02\x00\x00\x15\x00\x00\x04\x05\x00\x00\x00\x00eggs')

    def test_usbw(self):
        self.assertEqual(self.output.getvalue(), '')
        self.encoder.send('eggs', message.DOWNSTREAM_BANDWIDTH, 0, 21)
        self.assertEqual(self.output.getvalue(),
            '\x02\x00\x00\x15\x00\x00\x04\x05\x00\x00\x00\x00eggs')

    def test_other(self):
        self.assertEqual(self.output.getvalue(), '')
        self.encoder.send('eggs', message.INVOKE, 0, 21)
        self.assertEqual(self.output.getvalue(), '')


class CallbackTestCase(BaseTestCase):
    """
    Tests to ensure that a callback is executed once the RTMP message is
    completely encoded.
    """

    def setUp(self):
        BaseTestCase.setUp(self)

        self.executed = False

    def cb(self):
        self.executed = True

    def test_command(self):
        self.assertFalse(self.executed)
        self.encoder.send('eggs', message.CONTROL, 0, 0, self.cb)
        self.assertTrue(self.executed)

    def test_callback(self):
        self.assertFalse(self.executed)
        self.encoder.send('eggs', message.VIDEO_DATA, 0, 0, self.cb)
        self.assertFalse(self.executed)

        self.encoder.next()
        self.assertTrue(self.executed)

    def test_large(self):
        self.assertFalse(self.executed)
        self.encoder.send('a' * 1024, message.VIDEO_DATA, 0, 0, self.cb)

        while True:
            try:
                self.encoder.next()
            except StopIteration:
                break
            else:
                if self.executed is not True:
                    self.assertFalse(self.executed)

        self.assertTrue(self.executed)
