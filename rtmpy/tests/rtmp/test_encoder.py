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
Encoding tests for L{rtmpy.protocol.rtmp.codec}.
"""

import unittest

from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import codec
from rtmpy import message


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
        self.encoder.channelsInUse = codec.MAX_CHANNELS

        self.encoder.send('bar', 12, 2, 3)

        self.assertEqual(self.encoder.pending, [('bar', 12, 2, 3, None)])

        self.encoder.channelsInUse -= 1
        self.encoder.next()

        self.assertEqual(self.encoder.pending, [])


class AquireChannelTestCase(BaseTestCase):
    """
    Tests for L{codec.Encoder.acquireChannel}
    """

    def test_simple(self):
        self.assertEqual(self.encoder.channelsInUse, 0)

        c = self.encoder.acquireChannel()

        self.assertTrue(isinstance(c, codec.ProducingChannel))

        self.assertEqual(c.channelId, 1)
        self.assertEqual(c.header, None)

        self.assertEqual(self.encoder.channelsInUse, 1)

    def test_overflow(self):
        """
        Attempt to acquire MAX_CHANNELS + 1 channels.
        """

        self.encoder.channelsInUse = codec.MAX_CHANNELS - 1
        self.assertNotEqual(self.encoder.acquireChannel(), None)

        self.assertEqual(self.encoder.channelsInUse, codec.MAX_CHANNELS)
        self.assertEqual(self.encoder.acquireChannel(), None)


class ReleaseChannelTestCase(BaseTestCase):
    """
    Tests for L{codec.Encoder.releaseChannel}
    """

    def test_not_aquired(self):
        self.assertRaises(codec.EncodeError, self.encoder.releaseChannel, 3)

    def test_aquired(self):
        c = self.encoder.acquireChannel()

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
        self.assertEqual(self.output.read(),
            '\x03\x00\x00\x0f\x00\x00\x00\x07\x00\x00\x00\x00')
        self.output.truncate()

        self.encoder.send('', 7, 0, 15)
        self.encoder.next()

        self.output.seek(0)
        self.assertEqual(self.output.read(),
            '\x03\x00\x00\x00\x00\x00\x00\x07\x00\x00\x00\x00')
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
