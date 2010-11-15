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


class HeaderError(Exception):
    """
    Raised if a header related operation failed.
    """


class Header(object):
    """
    An RTMP Header. Holds contextual information for an RTMP Channel.
    """

    __slots__ = ('streamId', 'datatype', 'timestamp', 'bodyLength',
        'channelId', 'full', 'continuation')

    def __init__(self, channelId, timestamp=-1, datatype=-1,
                 bodyLength=-1, streamId=-1, full=False, continuation=False):
        self.channelId = channelId
        self.timestamp = timestamp
        self.datatype = datatype
        self.bodyLength = bodyLength
        self.streamId = streamId
        self.full = full
        self.continuation = continuation

    def __repr__(self):
        attrs = []

        for k in self.__slots__:
            v = getattr(self, k, None)

            if v == -1:
                v = None

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

    The channel id can be encoded in up to 3 bytes. The first byte is special as
    it contains the size of the rest of the header as described in
    L{getHeaderSize}.

    0 >= channelId > 64: channelId
    64 >= channelId > 320: 0, channelId - 64
    320 >= channelId > 0xffff + 64: 1, channelId - 64 (written as 2 byte int)

    @param stream: The stream to write the encoded header.
    @type stream: L{util.BufferedByteStream}
    @param header: The L{Header} to encode.
    @param previous: The previous header (if any).
    """
    if previous is None:
        size = 0
    else:
        if header.continuation:
            size = 0xc0
        else:
            size = min_bytes_required(header, previous)

    channelId = header.channelId

    if channelId < 64:
        stream.write_uchar(size | channelId)
    elif channelId < 320:
        stream.write_uchar(size)
        stream.write_uchar(channelId - 64)
    else:
        channelId -= 64

        stream.write_uchar(size + 1)
        stream.write_uchar(channelId & 0xff)
        stream.write_uchar(channelId >> 0x08)

    if size == 0xc0:
        return

    if size <= 0x80:
        if header.timestamp >= 0xffffff:
            stream.write_24bit_uint(0xffffff)
        else:
            stream.write_24bit_uint(header.timestamp)

    if size <= 0x40:
        stream.write_24bit_uint(header.bodyLength)
        stream.write_uchar(header.datatype)

    if size == 0:
        stream.endian = '<'
        stream.write_ulong(header.streamId)
        stream.endian = '!'

    if size <= 0x80:
        if header.timestamp >= 0xffffff:
            stream.write_ulong(header.timestamp)


def decode(stream):
    """
    Reads a header from the incoming stream.

    A header can be of varying lengths and the properties that get updated
    depend on the length.

    @param stream: The byte stream to read the header from.
    @type stream: C{pyamf.util.BufferedByteStream}
    @return: The read header from the stream.
    @rtype: L{Header}
    """
    # read the size and channelId
    channelId = stream.read_uchar()
    bits = channelId >> 6
    channelId &= 0x3f

    if channelId == 0:
        channelId = stream.read_uchar() + 64

    if channelId == 1:
        channelId = stream.read_uchar() + 64 + (stream.read_uchar() << 8)

    header = Header(channelId)

    if bits == 3:
        header.continuation = True

        return header

    header.timestamp = stream.read_24bit_uint()

    if bits < 2:
        header.bodyLength = stream.read_24bit_uint()
        header.datatype = stream.read_uchar()

    if bits < 1:
        # streamId is little endian
        stream.endian = '<'
        header.streamId = stream.read_ulong()
        stream.endian = '!'

        header.full = True

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

    # what to do about full/continuation flags?
    merged = Header(new.channelId)

    if new.streamId != -1:
        merged.streamId = new.streamId
    else:
        merged.streamId = old.streamId

    if new.bodyLength != -1:
        merged.bodyLength = new.bodyLength
    else:
        merged.bodyLength = old.bodyLength

    if new.datatype != -1:
        merged.datatype = new.datatype
    else:
        merged.datatype = old.datatype

    if new.timestamp != -1:
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
        return 0xc0

    if old.channelId != new.channelId:
        raise HeaderError('channelId mismatch on diff old=%r, new=%r' % (
            old, new))

    if old.streamId != new.streamId:
        return 0 # full header

    if old.datatype == new.datatype and old.bodyLength == new.bodyLength:
        if old.timestamp == new.timestamp:
            return 0xc0

        return 0x80

    return 0x40
