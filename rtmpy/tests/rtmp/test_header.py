# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.codec.header}.
"""

import unittest

from rtmpy.protocol import interfaces
from rtmpy.protocol.rtmp import header
from rtmpy import util, protocol


class MockHeader(object):
    """
    Pretend to be a header
    """

    datatype = None
    bodyLength = None
    streamId = None
    channelId = None
    relative = None
    timestamp = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


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
            'relative=True at 0x%x>' % (id(h),))

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
            'relative=False at 0x%x>' % (id(h),))

    def test_relative(self):
        h = header.Header(None)
        self.assertTrue(h.relative)

        h.channelId = 3
        self.assertTrue(h.relative)
        h.streamId = 4
        self.assertTrue(h.relative)
        h.bodyLength = 4
        self.assertTrue(h.relative)
        h.datatype = 4
        self.assertTrue(h.relative)
        h.timestamp = 4
        self.assertFalse(h.relative)


class DecodeHeaderByteTestCase(unittest.TestCase):
    """
    Tests for L{header.decodeHeaderByte}
    """

    def test_types(self):
        self.assertRaises(TypeError, header.decodeHeaderByte, 'asdfasd')

        try:
            header.decodeHeaderByte(123)
        except TypeError, e:
            self.fail('Unexpected TypeError raised')

    def test_return(self):
        self.assertEquals(header.decodeHeaderByte(0), (12, 0))
        self.assertEquals(header.decodeHeaderByte(192), (1, 0))
        self.assertEquals(header.decodeHeaderByte(255), (1, 63))


class EncodeHeaderByteTestCase(unittest.TestCase):
    """
    Tests for L{header.encodeHeaderByte}
    """

    def test_values(self):
        for x in header.HEADER_SIZES:
            try:
                header.encodeHeaderByte(x, 0)
            except header.HeaderError:
                self.fail('Raised header.HeaderError on %d' % (x,))

        self.assertFalse(16 in header.HEADER_SIZES)
        self.assertRaises(header.HeaderError, header.encodeHeaderByte, 16, 0)
        self.assertRaises(header.HeaderError, header.encodeHeaderByte, 1, -1)
        self.assertRaises(header.HeaderError, header.encodeHeaderByte, 1, 0x40)

    def test_return(self):
        self.assertEquals(header.encodeHeaderByte(12, 0), 0)
        self.assertEquals(header.encodeHeaderByte(1, 0), 192)
        self.assertEquals(header.encodeHeaderByte(1, 63), 255)


class GetHeaderSizeIndexTestCase(unittest.TestCase):
    """
    Tests for L{header.getHeaderSizeIndex}
    """

    def test_values(self):
        h = MockHeader()
        self.assertEquals(h.channelId, None)

        self.assertRaises(header.HeaderError, header.getHeaderSizeIndex, h)

    def test_return(self):
        h = MockHeader(channelId=3)

        self.assertEquals(
            [h.timestamp, h.datatype, h.bodyLength, h.streamId],
            [None, None, None, None])
        self.assertEquals(header.getHeaderSizeIndex(h), 3)
        self.assertEquals(
            [h.timestamp, h.datatype, h.bodyLength, h.streamId],
            [None, None, None, None])

        h.timestamp = 23455
        self.assertEquals(header.getHeaderSizeIndex(h), 2)

        h.datatype = 12
        h.bodyLength = 1234

        self.assertEquals(header.getHeaderSizeIndex(h), 1)
        h.timestamp = None
        e = self.assertRaises(header.HeaderError, header.getHeaderSizeIndex, h)

        h = MockHeader(channelId=23, streamId=234, bodyLength=1232,
            datatype=2, timestamp=234234)

        self.assertEquals(header.getHeaderSizeIndex(h), 0)

        h.bodyLength = None
        e = self.assertRaises(header.HeaderError, header.getHeaderSizeIndex, h)
        h.bodyLength = 1232

        h.datatype = None
        e = self.assertRaises(header.HeaderError, header.getHeaderSizeIndex, h)
        h.datatype = 2

        h.timestamp = None
        e = self.assertRaises(header.HeaderError, header.getHeaderSizeIndex, h)
        h.timestamp = 2345123


class GetHeaderSizeTestCase(unittest.TestCase):
    """
    Tests for L{header.getHeaderSize}
    """

    def test_return(self):
        h = MockHeader(channelId=3)

        self.assertEquals(
            [h.timestamp, h.datatype, h.bodyLength, h.streamId],
            [None, None, None, None])

        self.assertEquals(header.getHeaderSize(h), 1)
        h.timestamp = 234234
        self.assertEquals(header.getHeaderSize(h), 4)
        h.datatype = 2
        h.bodyLength = 1231211
        self.assertEquals(header.getHeaderSize(h), 8)
        h.streamId = 2134
        self.assertEquals(header.getHeaderSize(h), 12)


class EncodeHeaderTestCase(unittest.TestCase):
    """
    Tests for L{header.encodeHeader}
    """

    def setUp(self):
        self.stream = util.BufferedByteStream()

    def _encode(self, h):
        self.stream.seek(0, 2)
        self.stream.truncate()
        header.encodeHeader(self.stream, h)

        return self.stream.getvalue()

    def test_encode(self):
        h = MockHeader(channelId=3)

        self.assertEquals(
            [h.timestamp, h.datatype, h.bodyLength, h.streamId],
            [None, None, None, None])

        self.assertEquals(self._encode(h), '\xc3')

        h.channelId = 21
        self.assertEquals(self._encode(h), '\xd5')

        h.timestamp = 234234
        self.assertEquals(self._encode(h), '\x95\x03\x92\xfa')

        h.datatype = 3
        h.bodyLength = 31242
        self.assertEquals(self._encode(h), 'U\x03\x92\xfa\x00z\n\x03')

        h.streamId = 45
        self.assertEquals(self._encode(h),
            '\x15\x03\x92\xfa\x00z\n\x03-\x00\x00\x00')

    def test_extended_timestamp(self):
        h = MockHeader(channelId=34, timestamp=0x1000000)

        self.assertEquals(self._encode(h), '\xa2\xff\xff\xff\x01\x00\x00\x00')

        h.datatype = 3
        h.bodyLength = 31242
        self.assertEquals(self._encode(h),
            'b\xff\xff\xff\x00z\n\x03\x01\x00\x00\x00')

        h.streamId = 45
        self.assertEquals(self._encode(h),
            '"\xff\xff\xff\x00z\n\x03-\x00\x00\x00\x01\x00\x00\x00')


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
        self.assertEquals(h.relative, True)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

        h = self._decode('\xd5')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.relative, True)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

    def test_decodeSize4(self):
        h = self._decode('\x95\x03\x92\xfa')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.relative, True)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

    def test_decodeSize8(self):
        h = self._decode('U\x03\x92\xfa\x00z\n\x03')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.relative, True)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, None)

    def test_decodeSize12(self):
        h = self._decode('\x15\x03\x92\xfa\x00z\n\x03-\x00\x00\x00')

        self.assertEquals(h.channelId, 21)
        self.assertEquals(h.relative, False)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, 45)

    def test_extended_timestamp(self):
        h = self._decode('\xa2\xff\xff\xff\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.relative, True)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)

        h = self._decode('b\xff\xff\xff\x00z\n\x03\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.relative, True)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, None)

        h = self._decode(
            '"\xff\xff\xff\x00z\n\x03-\x00\x00\x00\x01\x00\x00\x00')

        self.assertEquals(h.channelId, 34)
        self.assertEquals(h.relative, False)
        self.assertEquals(h.timestamp, 0x1000000)
        self.assertEquals(h.bodyLength, 31242)
        self.assertEquals(h.datatype, 3)
        self.assertEquals(h.streamId, 45)


class DiffHeadersTestCase(unittest.TestCase):
    """
    Tests for L{header.diffHeaders}
    """

    def _generate(self):
        """
        Generates an absolute header and guarantees that the attributes will
        be the same on each call.
        """
        return MockHeader(relative=False, channelId=3, timestamp=1000,
            bodyLength=2000, datatype=3, streamId=243)

    def test_absolute(self):
        h1 = MockHeader(relative=None)
        h2 = MockHeader(relative=True)
        h3 = MockHeader(relative=False)

        self.assertRaises(header.HeaderError, header.diffHeaders, h1, h1)
        self.assertRaises(header.HeaderError, header.diffHeaders, h2, h2)
        self.assertRaises(header.HeaderError, header.diffHeaders, h3, h1)
        self.assertRaises(header.HeaderError, header.diffHeaders, h3, h2)

    def test_sameChannel(self):
        h1 = MockHeader(relative=False, channelId=3)
        h2 = MockHeader(relative=False, channelId=42)

        self.assertRaises(header.HeaderError, header.diffHeaders, h1, h2)

    def test_nodiff(self):
        old = self._generate()
        new = self._generate()

        h = header.diffHeaders(old, new)
        self.assertTrue(h.relative)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)
        self.assertEquals(h.channelId, 3)

    def test_timestamp(self):
        old = self._generate()
        new = self._generate()

        new.timestamp = old.timestamp + 234234
        h = header.diffHeaders(old, new)

        self.assertTrue(h.relative)
        self.assertEquals(h.timestamp, 235234)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)
        self.assertEquals(h.channelId, 3)

    def test_datatype(self):
        old = self._generate()
        new = self._generate()

        new.datatype = 0
        self.assertNotEquals(new.datatype, old.datatype)
        h = header.diffHeaders(old, new)

        self.assertTrue(h.relative)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, 0)
        self.assertEquals(h.streamId, None)
        self.assertEquals(h.channelId, 3)

    def test_bodyLength(self):
        old = self._generate()
        new = self._generate()

        new.bodyLength = 2001
        self.assertNotEquals(new.bodyLength, old.bodyLength)
        h = header.diffHeaders(old, new)

        self.assertTrue(h.relative)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, 2001)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, None)
        self.assertEquals(h.channelId, 3)

    def test_streamId(self):
        old = self._generate()
        new = self._generate()

        new.streamId = 12
        self.assertNotEquals(new.streamId, old.streamId)
        h = header.diffHeaders(old, new)

        self.assertTrue(h.relative)
        self.assertEquals(h.timestamp, None)
        self.assertEquals(h.bodyLength, None)
        self.assertEquals(h.datatype, None)
        self.assertEquals(h.streamId, 12)
        self.assertEquals(h.channelId, 3)

    def test_complex(self):
        old = self._generate()
        new = self._generate()

        new.streamId = 12
        new.timestamp = 234234
        new.datatype = 0
        new.bodyLength = 2001

        h = header.diffHeaders(old, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 2001)
        self.assertEquals(h.datatype, 0)
        self.assertEquals(h.streamId, 12)
        self.assertEquals(h.channelId, 3)


class MergeHeadersTestCase(unittest.TestCase):
    """
    Tests for L{header.mergeHeaders}
    """

    def setUp(self):
        self.absolute = MockHeader(relative=False, channelId=3,
            timestamp=1000, bodyLength=2000, datatype=3, streamId=243)

    def _generate(self):
        """
        Generates a relative header and with the same channelId on each call.
        """
        return MockHeader(relative=True, channelId=3)

    def test_absolute(self):
        h1 = MockHeader(relative=None)
        h2 = MockHeader(relative=True)
        h3 = MockHeader(relative=False)

        self.assertRaises(header.HeaderError, header.mergeHeaders, h1, h1)
        self.assertRaises(header.HeaderError, header.mergeHeaders, h2, h2)
        self.assertRaises(header.HeaderError, header.mergeHeaders, h3, h1)
        self.assertRaises(header.HeaderError, header.mergeHeaders, h2, h3)

    def test_sameChannel(self):
        h1 = MockHeader(relative=False, channelId=3)
        h2 = MockHeader(relative=True, channelId=42)

        self.assertRaises(header.HeaderError, header.mergeHeaders, h1, h2)

    def test_nodiff(self):
        new = self._generate()

        h = header.mergeHeaders(self.absolute, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, self.absolute.timestamp)
        self.assertEquals(h.bodyLength, self.absolute.bodyLength)
        self.assertEquals(h.datatype, self.absolute.datatype)
        self.assertEquals(h.streamId, self.absolute.streamId)
        self.assertEquals(h.channelId, self.absolute.channelId)

    def test_timestamp(self):
        new = self._generate()
        new.timestamp = 3

        h = header.mergeHeaders(self.absolute, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, 3)
        self.assertEquals(h.bodyLength, self.absolute.bodyLength)
        self.assertEquals(h.datatype, self.absolute.datatype)
        self.assertEquals(h.streamId, self.absolute.streamId)
        self.assertEquals(h.channelId, self.absolute.channelId)

    def test_datatype(self):
        new = self._generate()
        new.datatype = 7

        h = header.mergeHeaders(self.absolute, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, self.absolute.timestamp)
        self.assertEquals(h.bodyLength, self.absolute.bodyLength)
        self.assertEquals(h.datatype, 7)
        self.assertEquals(h.streamId, self.absolute.streamId)
        self.assertEquals(h.channelId, self.absolute.channelId)

    def test_bodyLength(self):
        new = self._generate()
        new.bodyLength = 42

        h = header.mergeHeaders(self.absolute, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, self.absolute.timestamp)
        self.assertEquals(h.bodyLength, 42)
        self.assertEquals(h.datatype, self.absolute.datatype)
        self.assertEquals(h.streamId, self.absolute.streamId)
        self.assertEquals(h.channelId, self.absolute.channelId)

    def test_streamId(self):
        new = self._generate()
        new.streamId = 31

        h = header.mergeHeaders(self.absolute, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, self.absolute.timestamp)
        self.assertEquals(h.bodyLength, self.absolute.bodyLength)
        self.assertEquals(h.datatype, self.absolute.datatype)
        self.assertEquals(h.streamId, 31)
        self.assertEquals(h.channelId, self.absolute.channelId)

    def test_complex(self):
        new = self._generate()

        new.streamId = 12
        new.timestamp = 234234
        new.datatype = 0
        new.bodyLength = 2001

        h = header.mergeHeaders(self.absolute, new)

        self.assertFalse(h.relative)
        self.assertEquals(h.timestamp, 234234)
        self.assertEquals(h.bodyLength, 2001)
        self.assertEquals(h.datatype, 0)
        self.assertEquals(h.streamId, 12)
        self.assertEquals(h.channelId, self.absolute.channelId)
