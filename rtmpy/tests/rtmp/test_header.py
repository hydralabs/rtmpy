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
Tests for L{rtmpy.rtmp.codec.header}.
"""

import unittest

from rtmpy.protocol.rtmp import header
from rtmpy import util


class HeaderTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.Header}
    """

    def test_init(self):
        h = header.Header(3)

        expected_attrs = {
            'channelId': 3,
            'timestamp': -1,
            'datatype': -1,
            'bodyLength': -1,
            'streamId':-1
        }

        for k, v in expected_attrs.items():
            self.assertEqual(getattr(h, k), v)

    def test_kwargs(self):
        d = {
            'channelId': 1,
            'timestamp': 50,
            'datatype': 20,
            'bodyLength': 2000,
            'streamId': 98,
        }

        h = header.Header(**d)

        for k, v in d.items():
            self.assertEqual(getattr(h, k), v)

    def test_repr(self):
        h = header.Header(3)

        self.assertEquals(repr(h), '<rtmpy.protocol.rtmp.header.Header '
            'streamId=None datatype=None timestamp=None bodyLength=None '
            'channelId=3 full=False continuation=False at 0x%x>' % (id(h),))

        d = {
            'channelId': 1,
            'timestamp': 50,
            'datatype': 20,
            'bodyLength': 2000,
            'streamId': 98,
        }

        h = header.Header(**d)

        self.assertEquals(repr(h), '<rtmpy.protocol.rtmp.header.Header '
            'streamId=98 datatype=20 timestamp=50 bodyLength=2000 channelId=1 '
            'full=False continuation=False at 0x%x>' % (id(h),))


class EncodeTestCase(unittest.TestCase):
    """
    Tests for L{header.encode}
    """

    def setUp(self):
        self.stream = util.BufferedByteStream()

        self.reset()

    def reset(self):
        self.old = header.Header(2, 3, 4, 5, 6)
        self.new = header.Header(2, 3, 4, 5, 6)

    def assertEncoded(self, bytes):
        self.stream.seek(0, 2)
        self.stream.truncate()
        header.encode(self.stream, self.new, self.old)

        self.assertEqual(self.stream.getvalue(), bytes)

    def test_size1(self):
        self.assertEncoded('\xc2')

        self.old.channelId = self.new.channelId = 21
        self.assertEncoded('\xd5')

    def test_size4(self):
        self.new.timestamp = 10

        self.assertEncoded('\x82\x00\x00\n')

    def test_size8(self):
        self.new.bodyLength = 150
        self.assertEncoded('B\x00\x00\x03\x00\x00\x96\x04')

        self.reset()

        self.new.datatype = 7
        self.assertEncoded('B\x00\x00\x03\x00\x00\x05\x07')

        # combo
        self.reset()
        self.new.bodyLength = 150
        self.new.datatype = 7
        self.assertEncoded('B\x00\x00\x03\x00\x00\x96\x07')

    def test_size12(self):
        self.new.streamId = 15
        self.assertEncoded('\x02\x00\x00\x03\x00\x00\x05\x04\x0f\x00\x00\x00')

    def test_extended_timestamp(self):
        self.new.timestamp = 0x1000000

        self.assertEncoded('\x82\xff\xff\xff\x01\x00\x00\x00')

    def test_extended_channelid(self):
        self.old = self.new
        h = self.new

        h.channelId = 3
        self.assertEncoded('\xc3')

        h.channelId = 63
        self.assertEncoded('\xff')

        h.channelId = 64
        self.assertEncoded('\xc0\x00')

        h.channelId = 65
        self.assertEncoded('\xc0\x01')

        h.channelId = 319
        self.assertEncoded('\xc0\xff')

        h.channelId = 320
        self.assertEncoded('\xc1\x00\x01')

        h.channelId = 65599
        self.assertEncoded('\xc1\xff\xff')


class DecodeTestCase(unittest.TestCase):
    """
    Tests for L{header.decode}
    """

    def _decode(self, s):
        stream = util.BufferedByteStream(s)

        return header.decode(stream)

    def test_decodeSize1(self):
        h = self._decode('\xc3')

        self.assertEquals(h.channelId, 3)
        self.assertEquals(h.timestamp, -1)
        self.assertEquals(h.bodyLength, -1)
        self.assertEquals(h.datatype, -1)
        self.assertEquals(h.streamId, -1)

        h = self._decode('\xd5')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, -1)
        self.assertEquals(h.bodyLength, -1)
        self.assertEquals(h.datatype, -1)
        self.assertEquals(h.streamId, -1)

    def test_decodeSize4(self):
        h = self._decode('\x95\x03\x92\xfa')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, -1)
        self.assertEquals(h.datatype, -1)
        self.assertEquals(h.streamId, -1)

    def test_decodeSize8(self):
        h = self._decode('U\x03\x92\xfa\x00z\n\x03')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, -1)

    def test_decodeSize12(self):
        h = self._decode('\x15\x03\x92\xfa\x00z\n\x03-\x00\x00\x00')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, 45)

    def test_extended_timestamp(self):
        h = self._decode('\xa2\xff\xff\xff\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, -1)
        self.assertEquals(h.datatype, -1)
        self.assertEquals(h.streamId, -1)

        h = self._decode('b\xff\xff\xff\x00z\n\x03\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, -1)

        h = self._decode(
            '"\xff\xff\xff\x00z\n\x03-\x00\x00\x00\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, 45)

    def test_extended_channelid(self):
        h = self._decode('\xc3')
        self.assertEqual(h.channelId, 3)

        h = self._decode('\xff')
        self.assertEqual(h.channelId, 63)

        h = self._decode('\xc0\x00')
        self.assertEqual(h.channelId, 64)

        h = self._decode('\xc0\xff')
        self.assertEqual(h.channelId, 319)

        h = self._decode('\xc1\x00\x00')
        self.assertEqual(h.channelId, 64)

        h = self._decode('\xc1\x01\x00')
        self.assertEqual(h.channelId, 65)

        h = self._decode('\xc1\xff\x00')
        self.assertEqual(h.channelId, 319)

        h = self._decode('\xc1\x00\x01')
        self.assertEqual(h.channelId, 320)

        h = self._decode('\xc1\xff\xff')
        self.assertEqual(h.channelId, 65599)


class MergeTestCase(unittest.TestCase):
    """
    Tests for L{header.merge}
    """

    def setUp(self):
        self.absolute = header.Header(3, timestamp=1000,
            bodyLength=2000, datatype=3, streamId=243)

    def merge(self, **kwargs):
        """
        Generates a relative header and with the same channelId on each call.
        """
        import copy

        h = copy.copy(self.absolute)

        for k, v in kwargs.items():
            setattr(h, k, v)

        return header.merge(self.absolute, h)

    def test_different_channels(self):
        self.assertRaises(header.HeaderError, self.merge, channelId=4)

    def test_timestamp(self):
        h = self.merge(timestamp=-1)

        self.assertEqual(h.timestamp, 1000)

        h = self.merge(timestamp=999)
        self.assertEqual(h.timestamp, 999)

    def test_datatype(self):
        h = self.merge(datatype=-1)

        self.assertEqual(h.datatype, 3)

        h = self.merge(datatype=4)
        self.assertEqual(h.datatype, 4)

    def test_bodyLength(self):
        h = self.merge(bodyLength=-1)

        self.assertEqual(h.bodyLength, 2000)

        h = self.merge(bodyLength=1500)
        self.assertEqual(h.bodyLength, 1500)

    def test_streamId(self):
        h = self.merge(streamId=-1)

        self.assertEqual(h.streamId, 243)

        h = self.merge(streamId=15)
        self.assertEqual(h.streamId, 15)
