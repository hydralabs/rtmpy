# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Channel type declarations.
"""

#: Changes the chunk size for packets
FRAME_SIZE = 0x01
# 0x02 is unknown
#: Send every x bytes read by both sides
BYTES_READ = 0x03
#: Ping is a stream control message, has subtypes
PING = 0x04
#: The servers downstream bandwidth
SERVER_BANDWIDTH = 0x05
#: The clients upstream bandwidth
CLIENT_BANDWIDTH = 0x06
#: Packet containing audio
AUDIO_DATA = 0x07
#: Packet containing video data
VIDEO_DATA = 0x08
# 0x0a - 0x0e is unknown
#: Shared object with variable length
FLEX_SHARED_OBJECT = 0x10
#: Shared message with variable length
FLEX_MESSAGE = 0x11
#: An invoke which does not expect a reply
NOTIFY = 0x12
#: Has subtypes
SHARED_OBJECT = 0x13
#: Like remoting call, used for stream actions too
INVOKE = 0x14
# 0x15 anyone?
#: FLV data
FLV_DATA = 0x16
