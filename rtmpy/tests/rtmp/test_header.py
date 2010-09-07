# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp.codec.header}.
"""

import unittest

from rtmpy.protocol import interfaces
from rtmpy.protocol.rtmp import header
from rtmpy import util, protocol


class HeaderTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.Header}
    """

    def test_init(self):
        h = header.Header(None)

        expected_attrs = {
            'channelId': None,
            'timestamp': None,
            'datatype': None,
            'bodyLength': None,
            'streamId': None
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
        h = header.Header(None)

        self.assertEquals(repr(h), '<rtmpy.protocol.rtmp.header.Header '
            'streamId=None datatype=None timestamp=None bodyLength=None '
            'channelId=None at 0x%x>' % (id(h),))

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
            'at 0x%x>' % (id(h),))


class EncodeHeaderTestCase(unittest.TestCase):
    """
    Tests for L{header.encodeHeader}
    """

    def setUp(self):
        self.stream = util.BufferedByteStream()

    def _encode(self, h, diff=None):
        self.stream.seek(0, 2)
        self.stream.truncate()
        header.encodeHeader(self.stream, h, diff)

        return self.stream.getvalue()

    def test_encode(self):
        h = header.Header(3)

        self.assertEquals(
            [h.timestamp, h.datatype, h.bodyLength, h.streamId],
            [None, None, None, None])

        self.assertEquals(self._encode(h, h), '\xc3')

        h.channelId = 21
        self.assertEquals(self._encode(h, h), '\xd5')

        other = header.Header(21)
        h.timestamp = 234234
        self.assertEquals(self._encode(h, other), '\x95\x03\x92\xfa')

        h.datatype = 3
        h.bodyLength = 31242
        self.assertEquals(self._encode(h, other), 'U\x03\x92\xfa\x00z\n\x03')

        h.streamId = 45
        self.assertEquals(self._encode(h),
            '\x15\x03\x92\xfa\x00z\n\x03-\x00\x00\x00')

    def test_extended_timestamp(self):
        h = header.Header(34, timestamp=0x1000000, datatype=0, streamId=0, bodyLength=0)

        self.assertEquals(self._encode(h),
            '\x22\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00')

        h.datatype = 3
        h.bodyLength = 31242
        self.assertEquals(self._encode(h),
            '\x22\xff\xff\xff\x00z\n\x03\x00\x00\x00\x00\x01\x00\x00\x00')

        h.streamId = 45
        self.assertEquals(self._encode(h),
            '"\xff\xff\xff\x00z\n\x03-\x00\x00\x00\x01\x00\x00\x00')

    def test_extended_channelid(self):
        h = header.Header(channelId=3)

        self.assertEquals(self._encode(h, h), '\xc3')

        h.channelId = 63
        self.assertEquals(self._encode(h, h), '\xff')

        h.channelId = 64
        self.assertEquals(self._encode(h, h), '\xc0\x00')

        h.channelId = 65
        self.assertEquals(self._encode(h, h), '\xc0\x01')

        h.channelId = 319
        self.assertEquals(self._encode(h, h), '\xc0\xff')

        h.channelId = 320
        self.assertEquals(self._encode(h, h), '\xc1\x00\x01')

        h.channelId = 65599
        self.assertEquals(self._encode(h, h), '\xc1\xff\xff')


class DecodeHeaderTestCase(unittest.TestCase):
    """
    Tests for L{header.decodeHeader}
    """

    def _decode(self, s):
        stream = util.BufferedByteStream(s)

        return header.decodeHeader(stream)

    def test_decodeSize1(self):
        h = self._decode('\xc3')

        self.assertEquals(h.channelId, 3)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

        h = self._decode('\xd5')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

    def test_decodeSize4(self):
        h = self._decode('\x95\x03\x92\xfa')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

    def test_decodeSize8(self):
        h = self._decode('U\x03\x92\xfa\x00z\n\x03')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, None)

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
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

        h = self._decode('b\xff\xff\xff\x00z\n\x03\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, None)

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

class DiffHeadersTestCase(unittest.TestCase):
    """
    Tests for L{header.diffHeaders}
    """

    def setUp(self):
        self.h = header.Header(3, timestamp=1000, bodyLength=2000,
            datatype=3, streamId=243)

    def diff(self, **kwargs):
        import copy

        h = copy.copy(self.h)

        for k, v in kwargs.items():
            setattr(h, k, v)

        return self.h.diff(h)

    def test_sameChannel(self):
        self.assertRaises(header.HeaderError, self.h.diff, header.Header(4))

    def test_nodiff(self):
        self.assertEqual(self.h.diff(self.h), 1)

    def test_timestamp(self):
        self.assertEqual(4, self.diff(timestamp=234234))

    def test_datatype(self):
        self.assertEqual(8, self.diff(datatype=23))

    def test_bodyLength(self):
        self.assertEqual(4, self.diff(bodyLength=5))

    def test_streamId(self):
        self.assertEqual(12, self.diff(streamId=12))


class MergeHeadersTestCase(unittest.TestCase):
    """
    Tests for L{header.mergeHeaders}
    """

    def setUp(self):
        self.absolute = header.Header(3, timestamp=1000,
            bodyLength=2000, datatype=3, streamId=243)
        self.empty = header.Header(3)

    def merge(self, **kwargs):
        """
        Generates a relative header and with the same channelId on each call.
        """
        import copy

        h = copy.copy(self.absolute)

        for k, v in kwargs.items():
            setattr(h, k, v)

        self.absolute.merge(h)

    def test_timestamp(self):
        self.merge(timestamp=None)

        self.assertEqual(self.absolute.timestamp, 1000)

        self.merge(timestamp=999)
        self.assertEqual(self.absolute.timestamp, 999)

    def test_datatype(self):
        self.merge(datatype=None)

        self.assertEqual(self.absolute.datatype, 3)

        self.merge(datatype=4)
        self.assertEqual(self.absolute.datatype, 4)

    def test_bodyLength(self):
        self.merge(bodyLength=None)

        self.assertEqual(self.absolute.bodyLength, 2000)

        self.merge(bodyLength=1500)
        self.assertEqual(self.absolute.bodyLength, 1500)

    def test_streamId(self):
        self.merge(streamId=None)

        self.assertEqual(self.absolute.streamId, 243)

        self.merge(streamId=15)
        self.assertEqual(self.absolute.streamId, 15)
