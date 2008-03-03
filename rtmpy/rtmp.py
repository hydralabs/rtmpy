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
from twisted.internet import reactor, protocol, defer, task
from twisted.python import log

from rtmpy.dispatcher import EventDispatcher
from rtmpy import util

RTMP_PORT = 1935

HEADER_BYTE = '\x03'
HEADER_SIZES = [12, 8, 4, 1]

HANDSHAKE_LENGTH = 1536
HANDSHAKE_SUCCESS = 'rtmp.handshake.success'
HANDSHAKE_FAILURE = 'rtmp.handshake.failure'
HANDSHAKE_TIMEOUT = 'rtmp.handshake.timeout'
DEFAULT_HANDSHAKE_TIMEOUT = 5.0 # seconds

PROTOCOL_ERROR = 'rtmp.protocol.error'

CHANNEL_COMPLETE = 'rtmp.channel.complete'
MAX_CHANNELS = 64

def _debug(obj, msg):
    print "%s<0x%x> - %s" %(obj.__class__.__name__, id(obj), msg)

def generate_handshake(uptime=None, ping=0):
    """
    Generates a handshake packet. If an uptime is not supplied, it is figured
    out automatically.

    @see: U{http://www.mail-archive.com/red5@osflash.org/msg04906.html}
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

def read_header(header, stream, byte_len):
    """
    Reads a header from the incoming stream.

    @param stream: The input buffer to read from
    @type stream: L{BufferedByteStream}
    @type byte_len: C{int}
    """
    assert byte_len in HEADER_SIZES, 'Unexpected header size'

    if byte_len == 1:
        return header

    header.relative = byte_len != 12

    if byte_len >= 4:
       header.timer = stream.read_3byte_uint()

    if byte_len >= 8:
       header.length = stream.read_3byte_uint()
       header.type = stream.read_uchar()

    if byte_len >= 12:
       header.stream_id = stream.read_ulong()

class RTMPHeader:
    """
    @ivar length: Length of the channel body.
    @type length: C{int}
    @ivar timer: A timer value.
    @type timer: C{int}
    @ivar relative: If the timer value is relative
    @type relative: C{bool}
    @ivar type: The data type of channel.
    @type type: C{int}
    """

    def __init__(self, channel, **kwargs):
        self.channel = channel

        self.relative = kwargs.get('relative', False)
        self.length = kwargs.get('length', None)
        self.timer = kwargs.get('timer', None)
        self.type = kwargs.get('type', None)
        self.stream_id = kwargs.get('stream_id', None)

    def channel_id(self):
        if not self.channel:
            return None

        return self.channel.channel_id

    channel_id = property(channel_id)


class RTMPChannel:
    """
    @ivar read: Number of bytes read from the stream so far.
    @type read: C{int}
    @ivar chunk_remaining: A calculated field that returns the number of bytes
        required to complete the current chunk.
    @type chunk_remaining: C{int}
    """

    chunk_size = 128
    read = 0

    def __init__(self, protocol, channel_id):
        self.protocol = protocol
        self.channel_id = channel_id

        self.header = RTMPHeader(self)
        self.body = util.BufferedByteStream()

    def _remaining(self):
        """
        Returns the number of bytes left to read from the stream.
        """
        return self.length - self.read

    remaining = property(_remaining)
    length = property(lambda self: self.header.length)

    def write(self, data):
        data_len = len(data)

        if self.read + data_len > self.length:
            raise OverflowError, 'Attempted to write too much data to the body'

        self.read += data_len
        self.body.write(data)

        if self.read >= self.length:
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

    def __repr__(self):
        return '<%s.%s channel_id=%d header=%r @ 0x%x>' % (self.__module__,
            self.__class__.__name__, self.channel_id, self.header, id(self))

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

    debug = False

    def connectionMade(self):
        if self.debug:
            _debug(self, "Connection made")

        protocol.Protocol.connectionMade(self)

        self.buffer = util.BufferedByteStream()
        self.state = RTMPBaseProtocol.HANDSHAKE
        self.my_handshake = None
        self.received_handshake = None

        # setup event observers
        self.addEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.addEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)

        self.setTimeout(self.handshakeTimeout, lambda: self.dispatchEvent(HANDSHAKE_TIMEOUT))

    def setTimeout(self, timeout, func):
        if self.debug:
            _debug(self, "Setting timeout: %s seconds" % timeout)

        if hasattr(self, '_timeout'):
            if not self._timeout.cancelled:
                self._timeout.cancel()

        self._timeout = reactor.callLater(timeout, func)

    def clearTimeout(self):
        if self.debug:
            _debug(self, "Clearing timeout")

        if not hasattr(self, '_timeout'):
            return

        if not self._timeout.cancelled and not self._timeout.called:
            if self.debug:
                _debug(self, "Cancelling timeout")
            self._timeout.cancel()

        del self._timeout

    def connectionLost(self, reason):
        """
        Called when the connection is lost for some reason.

        Cleans up any timeouts/buffer etc.
        """
        if self.debug:
            _debug(self, "Lost connection (reason:%s)" % reason)

        self.clearTimeout()
        self.buffer.truncate()
        self.channels = {}
        self.stopDecoding()

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

        if self.debug:
            _debug(self, "Creating channel %r" % channel)

        return channel

    def closeChannel(self, channel_id):
        """
        Closes a RTMP channel.

        @param channel_id: the index of the to channel be closed.
        @type channel_id: C{int}
        """
        if self.debug:
            _debug(self, "Closing channel %r" % self.channels[channel_id])

        del self.channels[channel_id]

    def decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol. Needs to be implemented
        by the subclass.

        @see: U{http://osflash.org/documentation/rtmp#handshake} for more info.
        """
        raise NotImplementedError

    def _decodeStream(self):
        """
        Attempts to unweave the RTMP stream. Splits and unweave the frames and
        dispatch them to the relevant channel.
        """
        self.buffer.seek(0)

        stream = self.buffer

        if self.current_channel is not None:
            chunk_length = min(stream.remaining(),
                self.current_channel.chunk_remaining)

            num_chunks = self.current_channel.chunks_received

            if chunk_length > 0:
                if self.debug:
                    _debug(self, "Writing %d bytes to channel %r" % (
                        chunk_length, self.current_channel))

                self.current_channel.write(stream.read(chunk_length))

            if self.current_channel.chunks_received != num_chunks:
                if self.debug:
                    _debug(self, "Received full chunk")
                self.current_channel = None

                return

        if self.current_channel is not None or stream.remaining() == 0:
            self.stopDecoding()

            return

        start_of_header = stream.tell()

        header_byte = stream.read_uchar()
        header_len = HEADER_SIZES[header_byte >> 6]

        if stream.remaining() < header_len - 1:
            # not enough stream left to continue decoding, rewind and wait
            if self.debug:
                _debug(self, "Insufficient data, rewinding (header_len:%d, stream_len:%d)" %(header_len, stream.remaining()))

            stream.seek(start_of_header)
            self.stopDecoding()

            return

        channel_id = header_byte & 0x3f
        try:
            self.current_channel = self.getChannel(channel_id)
        except KeyError:
            self.current_channel = self.createChannel(channel_id)

        read_header(self.current_channel.header, stream, header_len)

        # compare headers here

    def decodeStream(self):
        if self.debug:
            _debug(self, "Begin decoding stream buffer length: %d, channel: %r" % (len(self.buffer), self.current_channel))

        try:
            self._decodeStream()
        except:
            self.logAndDisconnect()
        else:
            if self.debug:
                _debug(self, "End decoding stream pos: %d, remaining: %d, current_channel: %r" % (
                    self.buffer.tell(), self.buffer.remaining(), self.current_channel))

            self.buffer.consume()

    def logAndDisconnect(self, failure=None):
        if self.debug:
            log.err()
            _debug(self, "error")
            raise

        self.transport.loseConnection()

    def stopDecoding(self):
        if self.debug:
            _debug(self, "Stopping decoding channel=%r" % self.current_channel)

        if hasattr(self, '_decoding_loop') and self._decoding_loop.running:
            self._decoding_loop.stop()

    def startDecoding(self):
        if not self._decoding_loop.running:
            d = self._decoding_loop.start(0)

            d.addErrback(lambda f: self.logAndDisconnect(f))

    def dataReceived(self, data):
        """
        Called when data is received from the underlying transport. Splits the
        data stream into chunks and delivers them to each channel.
        """
        if self.debug:
            _debug(self, "Receive data: state=%s, len=%d, stream.len=%d, stream.pos=%d" % (
                self.state, len(data), len(self.buffer), self.buffer.tell()))

        try:
            self.buffer.seek(0, 2)
            self.buffer.write(data)
            self.buffer.seek(0)

            if self.state == RTMPBaseProtocol.HANDSHAKE:
                self.decodeHandshake()
            elif self.state == RTMPBaseProtocol.STREAM:
                self.startDecoding()
        except:
            self.logAndDisconnect()

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
        
        self.channels = {}
        self.current_channel = None
        self.addEventListener(CHANNEL_COMPLETE, self.onChannelComplete)

        self.streams = {}
        self._decoding_loop = task.LoopingCall(self.decodeStream)

    def onHandshakeFailure(self, reason):
        """
        Called when the RTMP handshake failed for some reason. Drops the
        connection immediately.
        """
        if self.debug:
            _debug(self, "Failed handshake (reason:%s)" % reason)
        self.transport.loseConnection()

    def onHandshakeTimeout(self):
        """
        Called if the handshake was not successful within
        C{self.handshakeTimeout} seconds. Disconnects the peer.
        """
        if self.debug:
            _debug(self, "Handshake timedout")
        self.transport.loseConnection()

    def onChannelComplete(self, channel):
        """
        Called when a channel body has been completed.
        """
        if self.current_channel == channel:
            self.current_channel = None

        self.closeChannel(channel.channel_id)
