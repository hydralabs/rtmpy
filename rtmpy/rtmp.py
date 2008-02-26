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

HEADER_BYTE = '\x03'
HEADER_SIZES = [12, 8, 4, 1]

HANDSHAKE_LENGTH = 1536
HANDSHAKE_SUCCESS = 'rtmp.handshake.success'
HANDSHAKE_FAILURE = 'rtmp.handshake.failure'
HANDSHAKE_TIMEOUT = 'rtmp.handshake.timeout'
DEFAULT_HANDSHAKE_TIMEOUT = 5 # in seconds, can be a float

PROTOCOL_ERROR = 'rtmp.protocol.error'

CHANNEL_COMPLETE = 'rtmp.channel.complete'
MAX_CHANNELS = 64

def generate_handshake(uptime=None, ping=0):
    """
    Generates a handshake packet. If an uptime is not supplied, it is figured
    out automatically.

    @reference L{http://www.mail-archive.com/red5@osflash.org/msg04906.html}
    """
    if uptime is None:
        uptime = util.uptime()

    handshake = struct.pack("!I", uptime) + struct.pack("!I", ping)

    x = uptime

    for i in range(0, (HANDSHAKE_LENGTH - 8) / 2):
        x = (x * 0xb8cd75 + 1) & 0xff
        handshake += struct.pack("!H", x << 8)

    return handshake

def decode_handshake(data):
    """
    Decodes a handshake packet into a tuple (uptime, ping, data)

    @param data: C{str} or L{util.StringIO} instance
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

def read_header(channel, stream, byte_len):
    """
    Reads a header from the incoming stream.

    @type channel: L{RTMPChannel}
    @param stream: The input buffer to read from
    @type stream: L{BufferedByteStream}
    @type byte_len: C{int}
    """
    assert byte_len in HEADER_SIZES, 'Unexpected header size'

    if byte_len == 1:
        return

    if byte_len >= 4:
       channel.timer = stream.read(3)

    if byte_len >= 8:
       channel.length = (stream.read_ushort() << 8) + stream.read_uchar()
       channel.type = stream.read_uchar()

    if byte_len >= 12:
       channel.stream_id = stream.read_ulong()


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
    @ivar chunk_remaining: A calculated field that returns the number of bytes
        required to complete the current chunk.
    @type chunk_remaining: C{int}
    """

    chunk_size = 128
    read = 0
    timer = 0
    destination = 0
    length = 0

    def __init__(self, protocol, channel_id):
        self.protocol = protocol
        self.channel_id = channel_id
        self.body = util.BufferedByteStream()

    def _remaining(self):
        """
        Returns the number of bytes left to read from the stream.
        """
        return self.length - self.read

    remaining = property(_remaining)

    def write(self, data):
        data_len = len(data)

        if self.read + data_len > self.length:
            raise OverflowError, 'Attempted to write too much data to the body'

        self.read += data_len
        self.body.write(data)

        if self.read == self.length:
            self.body.seek(0)
            self.protocol.dispatchEvent(CHANNEL_COMPLETE, self)

    def chunk_remaining(self):
        if self.read >= self.length - (self.length % self.chunk_size):
            return self.length - self.read

        return self.chunk_size - (self.read % self.chunk_size)

    chunk_remaining = property(chunk_remaining)

    def chunks_received(self):
        if self.length < self.chunk_size:
            if self.read == self.length:
                return 1

            return 0

        if self.length == self.read:
            return self.read / self.chunk_size + 1

        return self.read / self.chunk_size

    chunks_received = property(chunks_received)


class RTMPBaseProtocol(protocol.Protocol, EventDispatcher):
    """
    I provide the basis for the initial handshaking phase and decoding rtmp
    packets as they arrive.

    @ivar buffer: Contains any remaining unparsed data from the C{transport}.
    @type buffer: L{util.BufferedByteStream}
    @ivar state: The state of the protocol.
    @type state: C{str}
    @ivar channels: A list of channels that are 'active'.
    @type channels: C{dict} of L{RTMPChannel}
    @ivar current_channel: The channel that is currently being written to/read
        from.
    @type current_channel: L{RTMPChannel} or None
    """

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    handshakeTimeout = DEFAULT_HANDSHAKE_TIMEOUT

    def connectionMade(self):
        protocol.Protocol.connectionMade(self)

        self.buffer = util.BufferedByteStream()
        self.channels = {}
        self.state = RTMPBaseProtocol.HANDSHAKE
        self.current_channel = None

        self.my_handshake = None
        self.received_handshake = None

        # setup event observers
        self.addEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.addEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)

        self.addEventListener(CHANNEL_COMPLETE, self.onChannelComplete)
        self.setTimeout(self.handshakeTimeout, lambda: self.dispatchEvent(HANDSHAKE_TIMEOUT))

    def setTimeout(self, timeout, func):
        if hasattr(self, '_timeout'):
            if not self._timeout.cancelled:
                self._timeout.cancel()

        self._timeout = reactor.callLater(timeout, func)

    def clearTimeout(self):
        if not hasattr(self, '_timeout'):
            return

        if not self._timeout.cancelled:
            self._timeout.cancel()

        del self._timeout

    def connectionLost(self, reason):
        """
        Called when the connection is lost for some reason.

        Cleans up any timeouts/buffer etc. 
        """
        self.clearTimeout()
        self.buffer.truncate()
        self.channels = {}

    def getChannel(self, channel_id):
        """
        Gets an existing channel for this connection.

        @param channel_id: Index for the channel to retrieve.
        @type channel_id: C{int}

        @raises IndexError: channel_id is out of range.
        @raises KeyError: No channel at specified index.

        @return: The existing channel.
        @rtype: L{RTMPChannel}
        """
        if channel_id >= MAX_CHANNELS or channel_id < 0:
            raise IndexError, "channel index %d is out of range" % channel_id

        try:
            return self.channels[channel_id]
        except KeyError:
            raise KeyError, "channel %d not found" % channel_id

    def createChannel(self, channel_id):
        """
        Creates a channel for the C{channel_id}.

        @param channel_id: The channel index for the new channel.
        @type channel_id: C{int}

        @raises IndexError: C{channel_id} is out of range.
        @raises KeyError: Channel already exists at that index.

        @return: The newly created channel.
        @rtype: L{RTMPChannel}
        """
        if channel_id >= MAX_CHANNELS or channel_id < 0:
            raise IndexError, "channel index %d is out of range" % channel_id

        if channel_id in self.channels.keys():
            raise KeyError, "channel index %d already exists" % channel_id

        channel = self.channels[channel_id] = RTMPChannel(self, channel_id)

        return channel

    def closeChannel(self, channel_id):
        """
        Closes a RTMP channel.

        @param: the index of the to channel be closed.
        @type: C{int}
        """
        del self.channels[channel_id]

    def decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol. Needs to be implemented
        by the subclass.

        @see L{http://osflash.org/documentation/rtmp#handshake} for more info.
        """
        raise NotImplementedError

    def decodeStream(self):
        """
        Attempts to unweave the RTMP stream. Splits and unweave the frames and
        dispatch them to the relevant channel.
        """
        stream = self.buffer

        while stream.remaining() > 0:
            if self.current_channel is not None:
                chunk_length = min(stream.remaining(),
                    self.current_channel.chunk_remaining)

                num_chunks = self.current_channel.chunks_received

                if chunk_length > 0:
                    self.current_channel.write(stream.read(chunk_length))

                if self.current_channel.chunks_received != num_chunks:
                    self.current_channel = None

            if self.current_channel is not None or stream.remaining() == 0:
                break

            start_of_header = stream.tell()

            header_byte = stream.read_uchar()
            header_len = HEADER_SIZES[header_byte >> 6]

            if stream.remaining() < header_len - 1:
                # not enough stream left to continue decoding, rewind and wait
                stream.seek(start_of_header)

                break

            channel_id = header_byte & 0x3f
            try:
                self.current_channel = self.getChannel(channel_id)
            except KeyError:
                self.current_channel = self.createChannel(channel_id)

            read_header(self.current_channel, stream, header_len)

    def dataReceived(self, data):
        """
        Called when data is received from the underlying transport. Splits the
        data stream into chunks and delivers them to each channel.

        @note: C{buffer}'s internal pointer is assumed to be at the end of the
            stream each time this function is called.
        """
        try:
            self.buffer.write(data)
            self.buffer.seek(0)

            if self.state == RTMPBaseProtocol.HANDSHAKE:
                self.decodeHandshake()
            elif self.state == RTMPBaseProtocol.STREAM:
                self.decodeStream()

            self.buffer.consume()
        except:
            self.transport.loseConnection()
            # TODO nick: logging

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
        self.clearTimeout()

    def onHandshakeFailure(self, reason):
        """
        Called when the RTMP handshake failed for some reason. Drops the
        connection immediately.
        """
        self.transport.loseConnection()

    def onHandshakeTimeout(self):
        """
        Called if the handshake was not successful within
        C{self.handshakeTimeout} seconds. Disconnects the peer.
        """
        self.transport.loseConnection()

    def onChannelComplete(self, channel):
        """
        Called when a channel body has been completed.
        """
        self.closeChannel(channel.channel_id)
