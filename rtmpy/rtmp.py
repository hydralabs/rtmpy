# -*- test-case-name: rtmpy.tests.test_rtmp -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
RTMP protocol for Twisted.

@author: U{Arnar Birgisson<mailto:arnarbi@gmail.com>}
@author: U{Thijs Triemstra<mailto:info@collab.nl>}
@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}

@since: 0.1.0
"""

import time, struct
from twisted.internet import reactor, protocol, defer

from rtmpy.dispatcher import EventDispatcher
from rtmpy import util

from pyamf.util import hexdump

RTMP_PORT = 1935

HEADER_SIZES = [12, 8, 4, 1]

HANDSHAKE_LENGTH = 1536
HANDSHAKE_SUCCESS = 'rtmp.handshake-success'
HANDSHAKE_FAILURE = 'rtmp.handshake-failure'
HANDSHAKE_TIMEOUT = 'rtmp.handshake-timeout'

HEADER_BYTE = '\x03'

DEFAULT_HANDSHAKE_TIMEOUT = 30 # seconds

def generate_handshake(uptime=None):
    """
    Generates a handshake packet. If an uptime is not supplied, it is figured
    out automatically.

    @reference L{http://www.mail-archive.com/red5@osflash.org/msg04906.html}
    """
    if uptime is None:
        uptime = util.uptime()

    handshake = struct.pack("!I", uptime) + struct.pack("!I", 0)

    x = uptime

    for i in range(0, (HANDSHAKE_LENGTH - 8) / 2):
        x = (x * 0xb8cd75 + 1) & 0xff
        handshake += struct.pack("!H", x << 8)

    return handshake


def decode_handshake(data):
    """
    Decodes a handshake packet into a tuple (uptime, data)

    @param data: C{str} or L{util.StringIO} instance
    """
    if not (hasattr(data, 'seek') and hasattr(data, 'read') and hasattr(data, 'close')):
        data = util.StringIO(data)

    data.seek(0)

    uptime = struct.unpack("!I", data.read(4))[0]
    body = data.read()

    data.close()

    return uptime, body


def read_header(channel, stream, byte_len):
    """
    Reads a header from the incoming stream.

    @type channel: L{RTMPChannel}
    @param stream: The input buffer to read from
    @type stream: L{BufferedByteStream}
    @type byte_len: C{int}
    """
    if byte_len == 1:
        return

    if byte_len >= 4:
       channel.unknown = stream.read(3)

    if byte_len >= 8:
       channel.length = (stream.read_ushort() << 8) + stream.read_uchar()
       channel.type = stream.read_uchar()

    if byte_len >= 12:
       channel.destination = stream.read_ulong()


class RTMPChannel:
    """
    @ivar length: Length of the body.
    @type length: C{int}
    @ivar unknown: 3 bytes of unknown data.
    @type unknown: C{str}
    @ivar type: The type of channel.
    @type type: C{int}
    @ivar read: Number of bytes read from the stream so far.
    @type read: C{int}
    """

    def __init__(self, protocol, channel_id):
        self.protocol = protocol
        self.channel_id = channel_id
        self.chunk_size = 128
        self.read = 0
        self.destination = 0

    def _remaining(self):
        """
        Returns the number of bytes left to read from the stream.
        """
        return self.length - self.read

    remaining = property(_remaining)

    def write(self, data):
        self.read += len(data)


class RTMPBaseProtocol(protocol.Protocol, EventDispatcher):
    """
    I provide the basis for the initial handshaking phase and parsing rtmp
    packets as they arrive.

    @ivar buffer: Contains any remaining unparsed data from the underlying
        transport.
    @type buffer: L{util.BufferedByteStream}
    @ivar state: The state of the protocol, used mainly in handshake negotiation.
    """

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    handshakeTimeout = DEFAULT_HANDSHAKE_TIMEOUT

    def connectionMade(self):
        protocol.Protocol.connectionMade(self)

        self.buffer = util.BufferedByteStream()
        self.channels = {}
        self.state = RTMPBaseProtocol.HANDSHAKE

        self.my_handshake = None
        self.received_handshake = None

        # setup event observers
        self.addEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.addEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)
        
        self._timeout = reactor.callLater(self.handshakeTimeout, lambda: self.dispatchEvent(HANDSHAKE_TIMEOUT))

    def _consumeBuffer(self):
        """
        A helper function that chops off the data that has already been read
        from the stream.
        """
        bytes = self.buffer.read()
        self.buffer.truncate()

        if len(bytes) > 0:
            self.buffer.write(bytes)
            self.buffer.seek(0)

    def getChannel(self, channel_id):
        try:
            channel = self.channels[channel_id]
        except KeyError:
            channel = self.channels[channel_id] = RTMPChannel(self, channel_id)

        return channel

    def dataReceived(self, data):
        """
        Called when data is received from the underlying transport. Splits the
        data stream into chunks and delivers them to each channel.
        """
        stream = self.buffer
        # seek to the end of the stream
        stream.seek(0, 2)
        stream.write(data)
        stream.seek(0)

        if self.state != RTMPBaseProtocol.STREAM:
            return

        while stream.remaining() > 0:
            header_byte = stream.read_uchar()
            header_len = HEADER_SIZES[header_byte >> 6]

            if stream.remaining() < header_len:
                return

            channel = self.getChannel(header_byte & 0x3f)
            read_header(channel, stream, header_len)

            chunk_length = min(channel.chunk_size,
                channel.remaining, stream.remaining())

            if chunk_length > 0:
                channel.write(stream.read(chunk_length))

        self._consumeBuffer()

    def onHandshakeSuccess(self):
        """
        Called when the RTMP handshake was successful. Once this is called,
        packet streaming can commence
        """
        # Remove the handshake timeout
        self._timeout.cancel()
        del self._timeout

        self.state = RTMPBaseProtocol.STREAM
        self.removeEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.removeEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)
        self.my_handshake = None
        self.received_handshake = None

    def onHandshakeFailure(self, reason):
        """
        Called when the RTMP handshake failed for some reason. Drops the
        connection immediately.
        """
        self.transport.loseConnection()
        self._timeout.cancel()
        del self._timeout

    def onHandshakeTimeout(self):
        """
        Called if the handshake was not successful within
        C{self.handshakeTimeout} seconds. Disconnects the peer.
        """
        self.transport.lostConnection()
        self._timeout.cancel()
        del self._timeout
