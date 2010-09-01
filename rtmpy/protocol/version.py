# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
"""

MAX_VERSION = 31
RTMP = 0x03

implementations = {
    RTMP: 'rtmp'
}


def get(version, default=None):
    return implementations.get(version, default)
