# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
Utility/helper functions for encoding and decoding RTMP headers.

@see: U{RTMP Packet Structure on OSFlash<http://osflash.org/documentation/rtmp
    #rtmp_packet_structure>}
"""

__all__ = [
    'Header',
    'encodeHeader',
    'decodeHeader',
]

#: The header can come in one of four sizes: 12, 8, 4, or 1 byte(s).
ENCODE_HEADER_SIZES = {12: 0, 8: 1, 4: 2, 1: 3}
DECODE_HEADER_SIZES = [12, 8, 4, 1]

#: A list of encoded headers
_ENCODED_CONTINUATION_HEADERS = []


class HeaderError(Exception):
    """
    Raised if a header related operation failed.
    """


class Header(object):
    """
    An RTMP Header. Holds contextual information for an RTMP Channel.

    @see: L{interfaces.IHeader}
    """

    __slots__ = ('streamId', 'datatype', 'timestamp', 'bodyLength', 'channelId')

    def __init__(self, channelId, timestamp=None, datatype=None,
                 bodyLength=None, streamId=None):
        self.channelId = channelId
        self.timestamp = timestamp
        self.datatype = datatype
        self.bodyLength = bodyLength
        self.streamId = streamId

    def merge(self, other):
        """
        Merge the values from C{other} into this header.

        @type other: L{Header}
        """
        if self is other:
            return

        if other.streamId is not None:
            self.streamId = other.streamId

        if other.datatype is not None:
            self.datatype = other.datatype

        if other.bodyLength is not None:
            self.bodyLength = other.bodyLength

        if other.timestamp is not None:
            self.timestamp = other.timestamp

    def diff(self, other):
        """
        Returns the number of bytes needed to de/encode the header based on the
        differences between the two.

        Both headers must be from the same channel.

        @param other: The other header to compare.
        @type old: L{Header}
        """
        if self is other:
            return 1

        if self.channelId != other.channelId:
            raise HeaderError('channelId mismatch on diff self=%r, other=%r' % (
                self, other))

        if self.streamId != other.streamId:
            return 12

        if self.datatype != other.datatype:
            return 8

        if self.bodyLength != other.bodyLength:
            return 4

        if self.timestamp != other.timestamp:
            return 4

        return 1

    def __repr__(self):
        attrs = []

        for k in self.__slots__:
            v = getattr(self, k, None)

            attrs.append('%s=%r' % (k, v))

        return '<%s.%s %s at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            ' '.join(attrs),
            id(self))


def encodeChannelId(stream, size, channelId):
    """
    Encodes the channel id to the stream.

    The channel id can be encoded in up to 3 bytes. The first byte is special as
    it contains the size of the rest of the header as described in
    L{getHeaderSize}.

    0 >= channelId > 64: channelId
    64 >= channelId > 320: 0, channelId - 64
    320 >= channelId > 0xffff + 64: 1, channelId - 64 (written as 2 byte int)
    """
    first = (ENCODE_HEADER_SIZES[size] << 6) & 0xff

    if channelId < 64:
        stream.write_uchar(first | channelId)
    elif channelId < 320:
        stream.write_uchar(first)
        stream.write_uchar(channelId - 64)
    else:
        channelId -= 64

        stream.write_uchar(first + 1)
        stream.write_uchar(channelId & 0xff)
        stream.write_uchar(channelId >> 0x08)


def encodeHeader(stream, header, previous=None):
    """
    Encodes a RTMP header to C{stream}.

    We expect the stream to already be in network endian mode.

    @param stream: The stream to write the encoded header.
    @type stream: L{util.BufferedByteStream}
    @param header: The L{Header} to encode.
    @param previous: The previous header (if any).
    """
    if previous is None:
        size = 12
    else:
        size = header.diff(previous)

    if size == 1 and header.channelId < 64:
        stream.write(_ENCODED_CONTINUATION_HEADERS[header.channelId])

        return

    encodeChannelId(stream, size, header.channelId)

    if size >= 4:
        if header.timestamp >= 0xffffff:
            stream.write_24bit_uint(0xffffff)
        else:
            stream.write_24bit_uint(header.timestamp)

    if size >= 8:
        stream.write_24bit_uint(header.bodyLength)
        stream.write_uchar(header.datatype)

    if size >= 12:
        stream.endian = 'little'
        stream.write_ulong(header.streamId)
        stream.endian = 'network'

    if size >= 4:
        if header.timestamp >= 0xffffff:
            stream.write_ulong(header.timestamp)


def decodeChannelId(stream):
    """
    Decodes the channel id and the size of the header from the stream.

    @return: C{tuple} containing the size of the header and the channel id.
    @see: L{encodeHeader} for an explanation of how the channelId is encoded.
    """
    channelId = stream.read_uchar()
    size = DECODE_HEADER_SIZES[channelId >> 6]
    channelId &= 0x3f

    if channelId > 1:
        return size, channelId & 0x3f
    elif channelId == 0:
        return size, stream.read_uchar() + 64
    else:
        return size, stream.read_uchar() + 64 + (stream.read_uchar() << 8)


def decodeHeader(stream):
    """
    Reads a header from the incoming stream.

    A header can be of varying lengths and the properties that get updated
    depend on the length. A header is relative if the length is not 12,
    this means that channel lengths and timers get updated accordingly.

    @param stream: The byte stream to read the header from.
    @type stream: C{rtmpy.util.BufferedByteStream}
    @return: The read header from the stream.
    @rtype: L{Header}
    """
    size, channelId = decodeChannelId(stream)
    header = Header(channelId)

    if size == 1:
        return header

    if size >= 4:
        header.timestamp = stream.read_24bit_uint()

    if size >= 8:
        header.bodyLength = stream.read_24bit_uint()
        header.datatype = stream.read_uchar()

    if size >= 12:
        # streamId is little endian
        stream.endian = '<'
        header.streamId = stream.read_ulong()
        stream.endian = '!'

    if header.timestamp == 0xffffff:
        header.timestamp = stream.read_ulong()

    return header


def build_header_continuations():
    global _ENCODED_CONTINUATION_HEADERS

    from pyamf.util import BufferedByteStream

    s = BufferedByteStream()

    # only generate the first 64 as it is likely that is all we will ever need
    for i in xrange(0, 64):
        encodeChannelId(s, 1, i)

        _ENCODED_CONTINUATION_HEADERS.append(s.getvalue())
        s.consume()


build_header_continuations()
