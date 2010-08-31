# Copyright the RTMPy Project.
# See LICENSE.txt for details.

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is primarily used
to stream audio and video over the internet to the U{Adobe Flash Player<http://
en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be
U{AMF<http://osflash.org/documentation/amf>} or raw audio/video data like
found in U{FLV<http://osflash.org/flv>}. A single connection is capable of
multiplexing many NetStreams using different channels. Within these channels
packets are split up into fixed size body chunks.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

#: The default RTMP port is a registered port at U{IANA<http://iana.org>}
RTMP_PORT = 1935

RTMPE_PROTOCOL_VERSION = 6
MAX_PROTOCOL_VERSION = 31

#: Maximum number of streams that can be active per RTMP stream
MAX_STREAMS = 0xffff
