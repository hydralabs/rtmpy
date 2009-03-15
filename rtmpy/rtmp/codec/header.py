# -*- test-case-name: rtmpy.tests.codec.test_header -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Utility/helper functions for encoding and decoding RTMP headers.

@see: U{RTMP Packet Structure on OSFlash
    (external)<http://osflash.org/documentation/rtmp#rtmp_packet_structure>}
"""

from rtmpy.rtmp.interfaces import IHeader
from rtmpy import rtmp, util

#: The header can come in one of four sizes: 12, 8, 4, or 1 byte(s).
HEADER_SIZES = [12, 8, 4, 1]


def decodeHeaderByte(byte):
    """
    Returns a tuple containing the decoded header length (in bytes) and the
    channel id from the header byte.

    @param byte: The header byte read from the stream.
    @type byte: C{int}
    @return: The header length and the channel id.
    @rtype: C{tuple}
    """
    if not isinstance(byte, int):
        raise TypeError('Expected an int (got %s)' % (type(byte),))

    if byte > 255 or byte < 0:
        raise OverflowError('Byte must be between 0 and 255 (got %d)' % (
            byte,))

    index = byte >> 6

    try:
        return HEADER_SIZES[index], byte & 0x3f
    except IndexError:
        raise ValueError('Invalid header size (got %d)' % (index,))


def encodeHeaderByte(headerLength, channelId):
    """
    Returns the encoded byte for a given C{headerLength} and C{channelId}.
    This is the reverse operation for L{decodeHeaderByte}.

    @param headerLength: The length of the header.
    @type headerLength: C{int}
    @param channelId: The channel id for the header.
    @type channelId: C{int}
    """
    if not isinstance(headerLength, int):
        raise TypeError('Expected an int for headerLength (got %s)' % (
            type(headerLength),))

    if not isinstance(channelId, int):
        raise TypeError('Expected an int for channelId (got %s)' % (
            type(channelId),))

    try:
        index = HEADER_SIZES.index(headerLength)
    except ValueError:
        raise ValueError('Unexpected headerLength value (got %d)' % (
            headerLength,))

    if channelId > 0x3f or channelId < 0:
        raise ValueError('Expected channelId between 0x00 and 0x3f')

    return (index << 6) | channelId


def getHeaderSizeIndex(header):
    """
    Calculates the RTMP header size for C{header}. At a minimum, the
    C{channelId} on C{header} needs to exist otherwise and L{ValueError}
    will be raised.

    @param header: An L{IHeader} object.
    @return: An index relating to L{HEADER_SIZES}.
    @rtype: C{int}
    """
    if not IHeader.providedBy(header):
        raise TypeError('IHeader interface expected')

    if header.channelId is None:
        raise ValueError('Header channelId cannot be None')

    if header.streamId is not None:
        if None in [header.bodyLength, header.datatype, header.timestamp]:
            raise ValueError('Dependant values unmet (got:%r)' % (header,))

        return 0

    if [header.bodyLength, header.datatype] != [None, None]:
        if header.timestamp is None:
            raise ValueError('Dependant values unmet (got:%r)' % (header,))

        return 1

    if header.timestamp is not None:
        # XXX : What should happen if header.streamId or header.datatype is
        # set? Whilst not strictly an error, it could be the result of some
        # corruption elsewhere.
        return 2

    return 3


def getHeaderSize(header):
    """
    Returns the expected number of bytes it will take to encode C{header}.

    @param header: An L{IHeader} object.
    @return: The number of bytes required to encode C{header}.
    @rtype: C{int}
    @raise ValueError: Unable to determine the header size.
    """
    index = getHeaderSizeIndex(header)

    try:
        return HEADER_SIZES[index]
    except IndexError:
        raise ValueError("Unable to determine header size (got %r)" % (
            header,))


def encodeHeader(stream, header):
    """
    Encodes a RTMP header to C{stream}.

    @param stream: The stream to write the encoded header.
    @type stream: L{util.BufferedByteStream}
    @param header: An I{IHeader} object.
    @raise TypeError: If L{IHeader} is not provided by C{header}.
    """
    if not IHeader.providedBy(header):
        raise TypeError('IHeader interface expected (got %s)' % (
            type(header),))

    if not isinstance(stream, util.BufferedByteStream):
        raise TypeError('BufferedByteStream expected (got %s)' % (
            type(stream),))

    def _encode():
        size = getHeaderSize(header)
        stream.write_uchar(encodeHeaderByte(size, header.channelId))

        if size == 1:
            return

        if size >= 4:
            stream.write_24bit_uint(header.timestamp)

        if size >= 8:
            stream.write_24bit_uint(header.bodyLength)
            stream.write_uchar(header.datatype)

        if size >= 12:
            stream.write_ulong(header.streamId)

    oldEndian = stream.endian
    stream.endian = util.BufferedByteStream.ENDIAN_NETWORK
    _encode()
    stream.endian = oldEndian


def decodeHeader(stream):
    """
    Reads a header from the incoming stream.

    A header can be of varying lengths and the properties that get updated
    depend on the length. A header is relative if the length is not 12,
    this means that channel lengths and timers get updated accordingly.

    @param stream: The byte stream to read the header from.
    @type stream: C{rtmpy.util.BufferedByteStream}
    @return: The read header from the stream.
    @rtype: L{rtmp.Header}
    """
    size, channelId = decodeHeaderByte(stream.read_uchar())
    relative = size != 12

    header = rtmp.Header(channelId=channelId, relative=relative)

    if size == 1:
        return header

    endian = stream.endian
    stream.endian = util.BufferedByteStream.ENDIAN_BIG

    if size >= 4:
        header.timestamp = stream.read_24bit_uint()

    if size >= 8:
        header.bodyLength = stream.read_24bit_uint()
        header.datatype = stream.read_uchar()

    if size >= 12:
        # streamId is little endian
        stream.endian = util.BufferedByteStream.ENDIAN_LITTLE
        header.streamId = stream.read_ulong()

    if header.timestamp == 0xffffff:
        stream.endian = util.BufferedByteStream.ENDIAN_BIG
        header.timestamp = stream.read_ulong()

    stream.endian = endian

    return header


def diffHeaders(old, new):
    """
    Returns a header based on the differences between two headers. Both C{old}
    and C{new} must implement L{IHeader}, be from the same channel and be
    absolute.

    @param old: The first header to compare.
    @type old: L{IHeader}
    @param new: The second header to compare.
    @type new: L{IHeader}
    @return: A header with the computed differences between old & new.
    @rtype: L{rtmp.Header}
    """
    if not IHeader.providedBy(old):
        raise TypeError("Expected IHeader for old (got %r)" % (old,))

    if not IHeader.providedBy(new):
        raise TypeError("Expected IHeader for new (got %r)" % (new,))

    if old.relative is not False:
        raise ValueError("Received a non-absolute header for old " \
            "(relative = %r)" % (old.relative))

    if new.relative is not False:
        raise ValueError("Received a non-absolute header for new " \
            "(relative = %r)" % (new.relative))

    if old.channelId != new.channelId:
        raise ValueError("The two headers are not for the same channel")

    header = rtmp.Header(channelId=old.channelId, relative=True)

    if new.timestamp != old.timestamp:
        header.timestamp = new.timestamp

    if new.datatype != old.datatype:
        header.datatype = new.datatype

    if new.bodyLength != old.bodyLength:
        header.bodyLength = new.bodyLength

    if new.streamId != old.streamId:
        header.streamId = new.streamId

    return header


def mergeHeaders(old, new):
    """
    Returns an absolute header that is the result of merging the values of
    C{old} and C{new}. Both C{old} and C{new} must implement L{IHeader} and be
    from the same channel. Also, C{old} must be absolute and C{new} must be
    relative.

    @param old: The first header to compare.
    @type old: L{IHeader}
    @param new: The second header to compare.
    @type new: L{IHeader}
    @return: A header with the merged values of old & new.
    @rtype: L{rtmp.Header}
    """
    if not IHeader.providedBy(old):
        raise TypeError("Expected IHeader for old (got %r)" % (old,))

    if not IHeader.providedBy(new):
        raise TypeError("Expected IHeader for new (got %r)" % (new,))

    if old.relative is not False:
        raise ValueError("Received a non-absolute header for old " \
            "(relative = %r)" % (old.relative))

    if new.relative is not True:
        raise ValueError("Received a non-relative header for new " \
            "(relative = %r)" % (new.relative))

    if old.channelId != new.channelId:
        raise ValueError("The two headers are not for the same channel")

    header = rtmp.Header(channelId=old.channelId, relative=False)

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
