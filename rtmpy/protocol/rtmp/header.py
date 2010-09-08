# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
Utility/helper functions for encoding and decoding RTMP headers.

@see: U{RTMP Packet Structure on OSFlash<http://osflash.org/documentation/rtmp
    #rtmp_packet_structure>}
"""

__all__ = [
    'Header',
    'encode',
    'decode',
    'merge'
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


def encode(stream, header, previous=None):
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
        size = min_bytes_required(header, previous)

    if size == 1 and header.channelId < 64:
        stream.write(_ENCODED_CONTINUATION_HEADERS[header.channelId])

        return

    _encodeChannelId(stream, size, header.channelId)

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


def decode(stream):
    """
    Reads a header from the incoming stream.

    A header can be of varying lengths and the properties that get updated
    depend on the length. A header is relative if the length is not 12,
    this means that channel lengths and timers get updated accordingly.

    @param stream: The byte stream to read the header from.
    @type stream: C{pyamf.util.BufferedByteStream}
    @return: The read header from the stream.
    @rtype: L{Header}
    """
    size, channelId = _decodeChannelId(stream)
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


def merge(old, new):
    """
    Merge the values of C{new} and C{old} together, returning the result.

    @type old: L{Header}
    @type new: L{Header}
    @rtype: L{Header}
    """
    if old.channelId != new.channelId:
        raise HeaderError('channelId mismatch on merge old=%r, new=%r' % (
            old.channelId, new.channelId))

    merged = Header(new.channelId)

    if new.streamId is not None:
        merged.streamId = new.streamId
    else:
        merged.streamId = old.streamId

    if new.bodyLength is not None:
        merged.bodyLength = new.bodyLength
    else:
        merged.bodyLength = old.bodyLength

    if new.datatype is not None:
        merged.datatype = new.datatype
    else:
        merged.datatype = old.datatype

    if new.timestamp is not None:
        merged.timestamp = new.timestamp
    else:
        merged.timestamp = old.timestamp

    return merged


def min_bytes_required(old, new):
    """
    Returns the number of bytes needed to de/encode the header based on the
    differences between the two.

    Both headers must be from the same channel.

    @type old: L{Header}
    @type new: L{Header}
    """
    if old is new:
        return 1

    if old.channelId != new.channelId:
        raise HeaderError('channelId mismatch on diff self=%r, other=%r' % (
            self, other))

    if old.streamId != new.streamId:
        return 12

    if old.datatype == new.datatype and old.bodyLength == new.bodyLength:
        if old.timestamp == new.timestamp:
            return 1

        return 4

    return 8


def _encodeChannelId(stream, size, channelId):
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


def _decodeChannelId(stream):
    """
    Decodes the channel id and the size of the header from the stream.

    @return: C{tuple} containing the size of the header and the channel id.
    @see: L{encodeHeader} for an explanation of how the channelId is encoded.
    """
    channelId = stream.read_uchar()
    bits = channelId >> 6
    channelId &= 0x3f

    if channelId == 0:
        channelId = stream.read_uchar() + 64

    if channelId == 1:
        channelId = stream.read_uchar() + 64 + (stream.read_uchar() << 8)

    return DECODE_HEADER_SIZES[bits], channelId


def build_header_continuations():
    global _ENCODED_CONTINUATION_HEADERS

    from pyamf.util import BufferedByteStream

    s = BufferedByteStream()

    # only generate the first 64 as it is likely that is all we will ever need
    for i in xrange(0, 64):
        _encodeChannelId(s, 1, i)

        _ENCODED_CONTINUATION_HEADERS.append(s.getvalue())
        s.consume()


build_header_continuations()
