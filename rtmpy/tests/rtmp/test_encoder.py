# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
Encoding tests for L{rtmpy.protocol.rtmp.codec}.
"""

import unittest

from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import codec


class BaseTestCase(unittest.TestCase):
    """
    Base functionality for other unit tests.
    """

    def setUp(self):
        self.output = BufferedByteStream()
        self.encoder = codec.Encoder(self.output)


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
            self.encoder.send('foo', 5, 6, 0)

        self.encoder.send('bar', 1, 2, 3)

        self.assertEqual(self.encoder.pending, [('bar', 1, 2, 3)])

        self.encoder.next()

        self.assertEqual(self.encoder.pending, [('bar', 1, 2, 3)])

        self.encoder.next()

        self.assertEqual(self.encoder.pending, [])


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
        self.encoder.send('b' * (128 + 50), 3, 0xfffe, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x81\x0f\x07\x00\x00\x00')
        self.assertEqual(self.output.read(128), 'a' * 128)
        self.assertEqual(self.output.read(12),
            '\x04\x00\x00\x00\x00\x00\xb2\x03\xfe\xff\x00\x00')
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
        self.encoder.send('a' * 2, 4, 5, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x02\x04\x05\x00\x00\x00')
        self.assertEqual(self.output.read(2), 'a' * 2)

        self.assertTrue(self.output.at_eof())
        self.output.consume()

        self.encoder.send('b' * 2, 6, 7, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x02\x06\x07\x00\x00\x00')
        self.assertEqual(self.output.read(2), 'b' * 2)

        self.assertTrue(self.output.at_eof())


class TimestampTestCase(BaseTestCase):
    """
    Tests to check for relative or absolute timestamps are encoded properly
    """

    def test_simple(self):
        # data, datatype, timestamp
        self.encoder.send('', 0, 0, 0)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(12),
            '\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')

        self.output.truncate()
        self.encoder.send('', 0, 0, 15)

        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(4), '\x83\x00\x00\x0f')
        self.output.truncate()

        self.encoder.send('', 3, 0, 15)
        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(8), '\x43\x00\x00\x00\x00\x00\x00\x03')
        self.output.truncate()
