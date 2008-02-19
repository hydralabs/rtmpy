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

RTMP_PORT = 1935

HEADER_SIZES = [12, 8, 4, 1]
HEADER_LENGTH_MASK = 0xc0

HANDSHAKE_LENGTH = 1536
HANDSHAKE_SUCCESS = 'rtmp.handshake-success'
HANDSHAKE_FAILURE = 'rtmp.handshake-failure'

HEADER_BYTE = '\x03'

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

class RTMPChannel(object):
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

    def remaining(self):
        """
        Returns the number of bytes left to read from the stream.
        """
        return self.length - self.read

    def write(self, data):
        pass


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

    def _consumeBuffer(self):
        """
        A helper function that chops off the data that has already been read
        from the stream.
        """
        self.buffer = util.BufferedByteStream(self.buffer.read())

    def _readHeader(self, stream, channel, header_len):
        """
        Reads a header from the incoming stream.
        """
        if header_len >= 4:
            channel.unknown = stream.read(3)

        if header_len >= 8:
            channel.length = stream.read_ushort() << 8 + stream.read_uchar()
            channel.type = stream.read_uchar()

        if header_len >= 12:
            channel.destination = stream.read_ulong()

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
        stream = util.BufferedByteStream(data)

        while stream.remaining() > 0:
            header_byte = stream.read_uchar()
            header_len = HEADER_SIZES[header_byte & HEADER_LENGTH_MASK]

            if stream.remaining() < header_len - 1:
                self.buffer.write(stream.read())

                return

            channel = self.getChannel(header_byte & 0xff)
            stream = self.buffer + stream
            stream.seek(1)

            self._readHeader(stream, channel, header_len)

            chunk_length = min(channel.chunk_size, channel.remaining(), stream.remaining())

            if chunk_length > 0:
                channel.write(stream.read(chunk_length))

        self.buffer.truncate()

    def onHandshakeSuccess(self):
        """
        Called when the RTMP handshake was successful. Once this is called,
        packet streaming can commence
        """
        self.state = RTMPBaseProtocol.STREAM
        self.removeEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.removeEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)
        self.my_handshake = None
        self.received_handshake = None

        # There shouldn't be any more data left in the buffer at this point -
        # it's our move next
        # XXX nick - what to do here? push any data back through dataReceived,
        #     be strict and disconnect, or truncate the buffer?
        if self.buffer.remaining() > 0:
            self.buffer.truncate()

    def onHandshakeFailure(self, reason):
        """
        Called when the RTMP handshake failed for some reason. Drops the
        connection immediately.
        """
        self.transport.loseConnection()
