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



class AquireChannelTestCase(BaseTestCase):
    """
    """

    def test_simple(self):
        self.assertEqual(self.encoder.channelsInUse, 0)

        c = self.encoder.aquireChannel()

        self.assertTrue(isinstance(c, codec.Channel))

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

    def test_simple(self):
        self.encoder.send('foobar', 0, 1)

        self.encoder.next()

        print repr(self.stream.getvalue())