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
    'diffHeaders',
    'mergeHeaders'
]

#: The header can come in one of four sizes: 12, 8, 4, or 1 byte(s).
ENCODE_HEADER_SIZES = {12: 0, 8: 1, 4: 2, 1: 3}
DECODE_HEADER_SIZES = [12, 8, 4, 1]


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

    def _get_relative(self):
        return None in [
            self.streamId,
            self.timestamp,
            self.datatype,
            self.bodyLength,
        ]

    relative = property(_get_relative)

    def __repr__(self):
        attrs = []

        for k in self.__slots__:
            v = getattr(self, k, None)

            if v is None:
                continue

            attrs.append('%s=%r' % (k, v))

        attrs.append('relative=%r' % (self.relative,))

        return '<%s.%s %s at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            ' '.join(attrs),
            id(self))


def getHeaderSize(header):
    """
    Returns the expected number of bytes it will take to encode C{header}.

    @param header: An L{interfaces.IHeader} object.
    @return: The number of bytes required to encode C{header}.
    @rtype: C{int}
    """
    if header.channelId is None:
        raise HeaderError('Header channelId cannot be None')

    if header.streamId is not None:
        if None in [header.bodyLength, header.datatype, header.timestamp]:
            raise HeaderError('Dependant values unmet (got:%r)' % (
                header,))

        return 12

    if [header.bodyLength, header.datatype] != [None, None]:
        if header.timestamp is None:
            raise HeaderError('Dependant values unmet (got:%r)' % (
                header,))

        return 8

    if header.timestamp is not None:
        return 4

    return 1


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


def encodeHeader(stream, header):
    """
    Encodes a RTMP header to C{stream}.

    We expect the stream to already be in network endian mode.

    @param stream: The stream to write the encoded header.
    @type stream: L{util.BufferedByteStream}
    @param header: An I{interfaces.IHeader} object.
    @raise TypeError: If L{interfaces.IHeader} is not provided by C{header}.
    """
    size = getHeaderSize(header)
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


def diffHeaders(old, new):
    """
    Returns a header based on the differences between two headers. Both C{old}
    and C{new} must implement L{interfaces.IHeader}, be from the same channel
    and be absolute.

    @param old: The first header to compare.
    @type old: L{interfaces.IHeader}
    @param new: The second header to compare.
    @type new: L{interfaces.IHeader}
    @return: A header with the computed differences between old & new.
    @rtype: L{Header}
    """
    if old.relative is not False:
        raise HeaderError("Received a non-absolute header for old "
            "(relative = %r)" % (old.relative))

    if new.relative is not False:
        raise HeaderError("Received a non-absolute header for new "
            "(relative = %r)" % (new.relative))

    if old.channelId != new.channelId:
        raise HeaderError("The two headers are not for the same channel")

    diff = Header(channelId=old.channelId)

    if new.timestamp != old.timestamp:
        diff.timestamp = new.timestamp

    if new.datatype != old.datatype:
        diff.datatype = new.datatype

    if new.bodyLength != old.bodyLength:
        diff.bodyLength = new.bodyLength
    elif diff.datatype is not None:
        diff.bodyLength = old.bodyLength

    if new.streamId != old.streamId:
        diff.streamId = new.streamId

    if diff.timestamp is None and diff.datatype is not None and diff.bodyLength is not None:
        diff.timestamp = 0

    return diff


def mergeHeaders(old, new):
    """
    Returns an absolute header that is the result of merging the values of
    C{old} and C{new}. Both C{old} and C{new} must implement
    L{interfaces.IHeader} and be from the same channel. Also, C{old} must be
    absolute and C{new} must be relative.

    @param old: The first header to compare.
    @type old: L{interfaces.IHeader}
    @param new: The second header to compare.
    @type new: L{interfaces.IHeader}
    @return: A header with the merged values of old & new.
    @rtype: L{Header}
    """
    if old.relative is not False:
        raise HeaderError("Received a non-absolute header for old "
            "(relative = %r)" % (old.relative))

    if new.relative is not True:
        raise HeaderError("Received a non-relative header for new "
            "(relative = %r)" % (new.relative))

    if old.channelId != new.channelId:
        raise HeaderError("The two headers are not for the same channel")

    header = Header(old.channelId)

    if new.timestamp is not None:
        header.timestamp = new.timestamp
    else:
        header.timestamp = old.timestamp

    if new.datatype is not None:
        header.datatype = new.datatype
    else:
        header.datatype = old.datatype

    if new.bodyLength is not None:
        header.bodyLength = new.bodyLength
    else:
        header.bodyLength = old.bodyLength

    if new.streamId is not None:
        header.streamId = new.streamId
    else:
        header.streamId = old.streamId

    return header
