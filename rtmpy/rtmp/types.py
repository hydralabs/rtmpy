# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Channel type declarations.
"""

FRAME_SIZE = 0x01
# 0x02 is unknown
BYTES_READ = 0x03
PING = 0x04
SERVER_BANDWIDTH = 0x05
CLIENT_BANDWIDTH = 0x06
AUDIO_DATA = 0x07
VIDEO_DATA = 0x08
# 0x0a - 0x0e is unknown
FLEX_SHARED_OBJECT = 0x10 # ?
FLEX_MESSAGE = 0x11
NOTIFY = 0x12
SHARED_OBJECT = 0x13
INVOKE = 0x14
# 0x15 anyone?
FLV_DATA = 0x16
