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
        self.encoder = codec.Encoder()
        self.stream = self.encoder.stream


class EncoderTestCase(BaseTestCase):
    """
    """

    def test_emtpy(self):
        self.assertRaises(StopIteration, self.encoder.next)

    def test_full(self):
        while not self.encoder.isFull():
            self.encoder.send('foo', 5, 6)

        self.encoder.send('bar', 1, 2, 3)

        self.assertEqual(self.encoder.pending, [('bar', 1, 2, 3)])

        self.encoder.next()

        self.assertEqual(self.encoder.pending, [('bar', 1, 2, 3)])

        self.encoder.next()

        self.assertEqual(self.encoder.pending, [])


class AquireChannelTestCase(BaseTestCase):
    """
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

        for i in xrange(0, 61):
            self.assertNotEqual(self.encoder.aquireChannel(), None)

        self.assertEqual(self.encoder.channelsInUse, 61)
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
    """

    def test_less_than_frame(self):
        self.encoder.send('foobar', 10, 1)

        self.encoder.next()

        self.assertEqual(self.stream.getvalue(),
            '\x03\x00\x00\x00\x00\x00\x06\n\x01\x00\x00\x00foobar')

        self.assertRaises(StopIteration, self.encoder.next)

    def test_multiple_frames(self):
        # 3 and a bit frames at 128 bytes per frame
        self.encoder.send('a' * (128 * 3 + 50), 10, 1)

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(12), '\x03\x00\x00\x00\x00\x01\xb2\n\x01\x00\x00\x00')
        self.assertEqual(self.stream.read(), 'a' * 128)
        self.assertTrue(self.stream.at_eof())

        self.stream.consume()

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(1), '\xc3')
        self.assertEqual(self.stream.read(), 'a' * 128)
        self.assertTrue(self.stream.at_eof())

        self.stream.consume()

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(1), '\xc3')
        self.assertEqual(self.stream.read(), 'a' * 128)
        self.assertTrue(self.stream.at_eof())

        self.stream.consume()

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(1), '\xc3')
        self.assertEqual(self.stream.read(), 'a' * 50)
        self.assertTrue(self.stream.at_eof())

        self.assertRaises(StopIteration, self.encoder.next)

    def test_interleave(self):
        # dispatch two messages
        self.encoder.send('a' * (128 + 1), 15, 7)
        self.encoder.send('b' * (128 + 50), 3, 0xfffe)

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(12), '\x03\x00\x00\x00\x00\x00\x81\x0f\x07\x00\x00\x00')
        self.assertEqual(self.stream.read(128), 'a' * 128)
        self.assertEqual(self.stream.read(12), '\x04\x00\x00\x00\x00\x00\xb2\x03\xfe\xff\x00\x00')
        self.assertEqual(self.stream.read(128), 'b' * 128)
        self.assertTrue(self.stream.at_eof())
        self.stream.consume()

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(1), '\xc3')
        self.assertEqual(self.stream.read(1), 'a')
        self.assertEqual(self.stream.read(1), '\xc4')
        self.assertEqual(self.stream.read(50), 'b' * 50)
        self.assertTrue(self.stream.at_eof())

    def test_reappropriate_channel(self):
        self.encoder.send('a' * 2, 4, 5)

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(12), '\x03\x00\x00\x00\x00\x00\x02\x04\x05\x00\x00\x00')
        self.assertEqual(self.stream.read(2), 'a' * 2)

        self.assertTrue(self.stream.at_eof())
        self.stream.consume()

        self.encoder.send('b' * 2, 6, 7)

        self.encoder.next()

        self.stream.seek(0)
        self.assertEqual(self.stream.read(12), '\x03\x00\x00\x00\x00\x00\x02\x06\x07\x00\x00\x00')
        self.assertEqual(self.stream.read(2), 'b' * 2)

        self.assertTrue(self.stream.at_eof())
