# -*- test-case-name: rtmpy.tests.test_rtmp -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is primarily used
to stream audio and video over the internet to the
U{Flash Player<http://en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be
U{AMF<http://osflash.org/documentation/amf>} or raw audio/video data like
found in U{FLV<http://osflash.org/flv>}. A single connection is capable of
multiplexing many NetStreams using different channels. Within these channels
packets are split up into fixed size body chunks.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}

@since: 0.1
"""

from twisted.internet import reactor, protocol, defer, task
from twisted.internet import interfaces as tw_interfaces
from twisted.python import log
from zope.interface import implements, providedBy
from pyamf.util import hexdump, IndexedCollection, BufferedByteStream

from rtmpy.rtmp import interfaces
from rtmpy.dispatcher import EventDispatcher
from rtmpy import util

#: Default port 1935 is a registered U{IANA<http://iana.org>} port.
RTMP_PORT = 1935

PROTOCOL_ERROR = 'rtmp.protocol.error'

MAX_CHANNELS = 64
MAX_STREAMS = 0xffff

DEBUG = True

class ChannelTypes:
    """
    RTMP Channel data types.
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


class Header(object):
    """
    An RTMP Header.
    """

    implements(interfaces.IHeader)

    def __init__(self, **kwargs):
        self.channelId = kwargs.get('channelId', None)
        self.timestamp = kwargs.get('timestamp', None)
        self.datatype = kwargs.get('datatype', None)
        self.bodyLength = kwargs.get('bodyLength', None)
        self.streamId = kwargs.get('streamId', None)

        self.relative = kwargs.get('relative', None)


class Channel(object):
    """
    Acts as a container for an RTMP channel. Does not know anything of
    encoding or decoding channels, it is literally meant as a dump from the
    protocol.

    A channel is meant to to agnostic to whether it is a producing channel
    (receiving data from the stream) or a consuming channel (receiving data
    from the connection).

    @ivar manager: The manager for this channel. The channel will report back
        to the manager about various activities it is performing.
    @type manager: L{ChannelManager}
    @ivar header: The calculated header for this channel. RTMP can send
        relative headers, which will be merged with the previous headers to
        calculate the absolute values for the header.
    @type header: L{Header}

    NJ: not sure about this lot ..
    @ivar bytesRecieved: Number of bytes read from the stream so far.
    @type bytesRecieved: C{int}
    @ivar framesRecieved: A calculated field that returns the number of bytes
        required to complete the current chunk.
    @type framesRecieved: C{int}
    """

    implements(interfaces.IChannel)

    def registerManager(self, manager):
        """
        Registers this channel to C{manager}.

        @type manager: L{ChannelManager}
        """
        self.manager = manager
        self.reset()

    def getHeader(self):
        """
        Gets the header for this channel. The header contains the absolute
        values for all received headers in the stream.
        """
        return self.header

    def setHeader(self, header):
        assert IHeader.providedBy(header), "Expected header to implement IHeader"

        # TODO: merge the header here
        self.header = header

    def reset(self):
        """
        """
        self.clear()

        self._frameRemaining = self.manager.getFrameSize()
        self.bytes = 0
        self.frames = 0
        self.header = None

    def clear(self):
        """
        """
        self.frame = BufferedByteStream()

    def write(self, data):
        """
        Called when a frame or partial frame is read from or written to the
        RTMP byte stream. If an entire frame (or multiple frames) completed,
        then L{dispatchFrame} is called. Note that the number of frames and
        the number of times that L{dispatchFrame} is called may not necessarily
        be the same.

        @param data: A string of bytes.
        @type data: C{str}
        """
        if self.header is None:
            raise RuntimeError("Cannot write to a channel with no header")

        frameSize = self.manager.getFrameSize()
        dataLength = len(data)

        if dataLength < self._frameRemaining:
            # we won't be completing any frames this time.
            self.bytes += dataLength
            self.frame.write(data)
            self._frameRemaining -= dataLength

            return

        self.bytes += self._frameRemaining
        self.frame.write(data[:self._frameRemaining - 1])
        dataLength -= self._frameRemaining

        # we now have a full frame
        self.dispatchFrame()

        while dataLength >= frameSize:
            data = data[:frameSize - 1]
            self.write(data)
            dataLength -= frameSize

        self.bytes += dataLength
        self.packet.write(data)
        self._frameRemaining = frameSize - dataLength

    def dispatchFrame(self):
        self.manager.frameReceived(self, self.packet.getvalue())
        self.clear()
        self.frames += 1

    def channelId(self):
        if self.header is None:
            raise AttributeError("No channelId without a header")

        return self.header.channelId

    channelId = property(channelId)

    def bodyRemaining(self):
        return self.header.bodyLength - len(self.buffer)

    bodyRemaining = property(bodyRemaining)


class ChannelManager(object):
    """
    Manages the creation/deletion and general maintenance of the channels
    linked to a connected RTMP Protocol. Also handles any events that channels
    may fire.

    @ivar channels: A list of channels.
    @type channels: C{dict} of L{Channel}
    """

    implements(interfaces.IChannelManager)

    channels = {}

    def getChannel(self, channelId):
        """
        Returns a channel based on channelId. If the channel doesn't exist,
        then C{None} is returned.

        @param channelId: Index for the channel to retrieve.
        @type channelId: C{int}
        @rtype: L{Channel}
        """
        if MAX_CHANNELS < channelId < 0:
            raise IndexError("channelId is out of range (got:%d)" % (channelId,))

        try:
            return self.channels[channelId]
        except KeyError:
            return None

    def createChannel(self):
        """
        Creates and returns a newly created channel. The channel is registered
        to the first available channelId (see L{getNextAvailableChannelId}).

        @return: The newly created channel.
        @rtype: L{RTMPChannel}
        @raise OverflowError: No free channelId available.
        """

        # XXX: RTMPChannel doesn't exist?
        channel = self._channels[channel_id] = RTMPChannel(self, self.protocol, channel_id)

        if self.protocol.debug:
            _debug(self, "Creating channel %d, %r" % (channel_id, channel))

        return channel

    def removeChannel(self, channel_id):
        """
        Removes a RTMP channel.

        @param channel_id: The index of the to channel be closed.
        @type channel_id: C{int}
        """
        if channel_id >= self.max_channels or channel_id < 0:
            raise IndexError, "channel index %d is out of range" % channel_id

        if self.protocol.debug:
            _debug(self, "Removing channel %d, %r" % (channel_id, self._channels[channel_id]))

        del self._channels[channel_id]

    def getNextAvailableChannelId(self):
        """
        Returns a free channelId.
        """
        keys = self.channels.keys()

        if len(keys) == MAX_CHANNELS:
            raise OverflowError("No free channel")

        count = 0

        while count < MAX_CHANNELS:
            try:
                if keys[count] != count:
                    return count
            except IndexError:
                return count

            count += 1

        return count

    def onCompleteBody(self, channel):
        """
        Called when a channel has received all of its data.
        
        @note: This may change to C{onData} at some point as we start to look
            at streaming larger chunks of data, e.g. video/audio
        """
        self.removeChannel(channel.channel_id)

class Context(ChannelManager):
    pass

class BaseProtocol(protocol.Protocol, EventDispatcher):
    """
    Provides the basis for the initial handshaking phase and decoding RTMP
    packets as they arrive.

    @ivar buffer: Contains any remaining unparsed data from the C{transport}.
    @type buffer: L{util.BufferedByteStream}
    @ivar state: The state of the protocol. Can be either C{HANDSHAKE} or
        C{STREAM}.
    @type state: C{str}
    """

    chunk_size = 128

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    #handshakeTimeout = DEFAULT_HANDSHAKE_TIMEOUT
    debug = False

    def connectionMade(self):
        if self.debug:
            _debug(self, "Connection made")

        protocol.Protocol.connectionMade(self)

        self.state = BaseProtocol.HANDSHAKE
        self.buffer = util.BufferedByteStream()
        self.my_handshake = None
        self.received_handshake = None

        # setup event observers
        self.addEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.addEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)

        self.setTimeout(self.handshakeTimeout,
            lambda: self.dispatchEvent(HANDSHAKE_TIMEOUT))

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
        self.channel_manager = None
        self.stream_manager = None

        if hasattr(self, 'decoder'):
            self.decoder.stop()
            self.decoder = None

        if hasattr(self, 'encoder'):
            self.encoder.stop()
            self.encoder = None

    def decodeHandshake(self, data):
        """
        Negotiates the handshake phase of the protocol. Needs to be implemented
        by the subclass.

        @see: U{RTMP handshake on OSFlash (external)
        <http://osflash.org/documentation/rtmp#handshake>} for more info.
        """
        raise NotImplementedError

    def decodeStream(self, data):
        self.decoder.dataReceived(data)
        self.decoder.start()

    def logAndDisconnect(self, failure=None):
        if self.debug:
            log.err()
            _debug(self, "error")

        self.transport.loseConnection()

        if self.debug:
            raise

    def decodeData(self, data):
        """
        Decodes data from the stream. This is not decoding RTMP but used to
        preprocess the data before it is passed to the stream decoding api.

        This function mainly exists so that protocols like RTMPE can be
        handled gracefully.

        @param data: The string of bytes received from the underlying
            connection.
        @return: The decoded data.
        @rtype: C{str}
        """
        return data

    def dataReceived(self, data):
        """
        Called when data is received from the underlying transport. Splits the
        data stream into chunks and delivers them to each channel.
        """
        data = self.decodeData(data)

        if self.debug:
            _debug(self, "Receive data: state=%s, len=%d, stream.len=%d, stream.pos=%d" % (
                self.state, len(data), len(self.buffer), self.buffer.tell()))

        try:
            if self.state is BaseProtocol.HANDSHAKE:
                self.decodeHandshake(data)
            elif self.state is BaseProtocol.STREAM:
                self.decodeStream(data)
        except:
            self.logAndDisconnect()

    def onHandshakeSuccess(self):
        """
        Called when the RTMP handshake was successful. Once this is called,
        packet streaming can commence.
        """
        self.state = BaseProtocol.STREAM
        self.removeEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.removeEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)
        self.my_handshake = None
        self.received_handshake = None
        self.clearTimeout()

        self.channel_manager = ChannelManager(self)
        self.stream_manager = StreamManager(self)

        self.decoder = ProtocolDecoder(self)
        self.encoder = ProtocolEncoder(self)

        self.core_stream = self.stream_manager.createStream(0, immutable=True)

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

    def registerProducingChannel(self, channel):
        self.encoder.registerChannel(channel)
