# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake.

@since: 0.1
"""

SECRET_KEY = '\x47\x65\x6e\x75\x69\x6e\x65\x20\x41\x64\x6f\x62\x65\x20' + \
    '\x46\x6c\x61\x73\x68\x20\x4d\x65\x64\x69\x61\x20\x53\x65\x72\x76' + \
    '\x65\x72\x20\x30\x30\x31\xf0\xee\xc2\x4a\x80\x68\xbe\xe8\x2e\x00' + \
    '\xd0\xd1\x02\x9e\x7e\x57\x6e\xec\x5d\x2d\x29\x80\x6f\xab\x93\xb8' + \
    '\xe6\x36\xcf\xeb\x31\xae'

#: First single byte in the handshake request.
HEADER_BYTE = '\x03'

HANDSHAKE_LENGTH = 1536
DEFAULT_HANDSHAKE_TIMEOUT = 5.0 # seconds


def generate_handshake(uptime=None, ping=0):
    """
    Generates a handshake packet. If an C{uptime} is not supplied, it is
    figured out automatically.

    @see: U{Red5 mailinglist (external)
    <http://www.mail-archive.com/red5@osflash.org/msg04906.html>}
    """
    if uptime is None:
        uptime = util.uptime()

    handshake = HEADER_BYTE + struct.pack("!I", uptime) + struct.pack("!I", ping)

    x = uptime

    for i in range(0, (HANDSHAKE_LENGTH - 10) / 2):
        x = (x * 0xb8cd75 + 1) & 0xff
        handshake += struct.pack("!H", x << 8)

    handshake += '\x00'
    return handshake

def decode_handshake(data):
    """
    Decodes a handshake packet into a C{tuple} (C{uptime}, C{ping}, C{data}).

    @param data: C{str} or L{util.BufferedByteStream} instance
    """
    created = False

    if not isinstance(data, util.BufferedByteStream):
        data = util.BufferedByteStream(data)
        created = True

    data.seek(0)

    uptime = data.read_ulong()
    ping = data.read_ulong()
    body = data.read()

    if created:
        data.close()

    return uptime, ping, body
