# -*- test-case-name: rtmpy.tests.test_rtmp -*-

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
"""

from twisted.internet import reactor, protocol, defer, task
from zope.interface import implements
from pyamf.util import IndexedCollection, BufferedByteStream

from rtmpy.rtmp import interfaces
from rtmpy.dispatcher import EventDispatcher


#: The default RTMP port is a registered at U{IANA<http://iana.org>}.
RTMP_PORT = 1935

DEFAULT_FRAME_SIZE = 128
MAX_CHANNELS = 64
MAX_STREAMS = 0xffff

DEBUG = False


class BaseError(Exception):
    """
    A base class for all RTMP related errors.
    """


class HeaderError(BaseError):
    """
    Raised if a header related operation failed.
    """


class NoManagerError(BaseError):
    """
    Raised if an operation performed on a channel requires a registered
    manager
    """


def log(obj, msg):
    """
    Used to log interesting messages from within this module (and submodules).
    Should only be called if L{DEBUG} = C{True}
    """
    print repr(obj), msg


class Header(object):
    """
    An RTMP Header. Holds contextual information for an RTMP Channel.

    @see: L{interfaces.IHeader}
    """

    implements(interfaces.IHeader)

    def __init__(self, **kwargs):
        self.channelId = kwargs.get('channelId', None)
        self.timestamp = kwargs.get('timestamp', None)
        self.datatype = kwargs.get('datatype', None)
        self.bodyLength = kwargs.get('bodyLength', None)
        self.streamId = kwargs.get('streamId', None)

        self.relative = kwargs.get('relative', None)

    def __repr__(self):
        s = ['%s=%r' % (k, v) for k, v in self.__dict__.iteritems()]

        s = '<%s.%s %s at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            ' '.join(s),
            id(self))

        return s


class Channel(object):
    """
    Acts as a container for an RTMP channel. Does not know anything of
    encoding or decoding channels, it is literally meant as a proxy between
    the byte stream and an observer.

    @ivar manager: The manager for this channel. The channel will report back
        to the manager about various activities it is performing.
    @type manager: L{ChannelManager}
    @ivar header: The calculated header for this channel. RTMP can send
        relative headers, which will be merged with the previous headers to
        calculate the absolute values for the header.
    @type header: L{Header} or C{None}
    @ivar frameRemaining: The amount of data that needs to be received before
        a frame can be considered complete.
    @type frameRemaining: C{int}
    @ivar buffer: Any buffered data before an observer was registered.
    @type buffer: C{str} or C{None}
    """

    implements(interfaces.IChannel)

    def __init__(self):
        self.manager = None
        self.header = None
        self.buffer = None
        self.observer = None

    def registerManager(self, manager):
        """
        Registers a manager to this channel.
        """
        if not interfaces.IChannelManager.providedBy(manager):
            raise TypeError('Expected IChannelManager for manager ' \
                '(got %s)' % (type(manager),))

        self.manager = manager

    def registerObserver(self, observer):
        """
        Registers an observer to this channel. If there is any buffered data,
        the observer will be notified immediately.

        @param observer: The observer for this channel.
        @type observer: L{interfaces.IChannelObserver}
        """
        if not interfaces.IChannelObserver.providedBy(observer):
            raise TypeError('Expected IChannelObserver for observer ' \
                '(got %s)' % (type(observer),))

        self.observer = observer

        if hasattr(self, 'buffer') and self.buffer is not None:
            self.observer.dataReceived(self.buffer)
            self.buffer = None

    def reset(self):
        """
        Called to reset the channel's context.

        @note: Does not reset any header information that may already be
            applied to this channel.
        @raise ChannelError: If no manager has been registered.
        """
        if self.manager is None:
            raise NoManagerError('Resetting a channel requires a ' \
                'registered manager')

        self.frameRemaining = self.manager.frameSize
        self.frames = 0
        self.bytes = 0
        self.buffer = None
        self.observer = None
        self.bodyRemaining = None

    def getHeader(self):
        """
        Gets the header for this channel. The header contains the absolute
        values for all received headers in the stream.

        @rtype: L{interfaces.IHeader} or C{None}
        """
        return self.header

    def setHeader(self, header):
        """
        Applies a new header to this channel. If this channel has no previous
        header then the new header must be absolute (relative=True). Otherwise
        the new values will be applied to the existing header. Setting the
        header requires a registered manager.

        @param header: The header to apply to this channel.
        @type header: L{interfaces.IHeader}
        """
        if DEBUG:
            log(self, 'setHeader(%s)' % (header,))

        if not interfaces.IHeader.providedBy(header):
            raise TypeError("Expected header to implement IHeader")

        if self.manager is None:
            raise NoManagerError('Setting the header requires a registered ' \
                'manager')

        if self.header is None:
            if header.relative is True:
                raise HeaderError('Tried to set a relative header as ' \
                    'absolute')
        else:
            if header.channelId != self.header.channelId:
                raise HeaderError('Tried to assign a header from a ' \
                    'different channel (original:%d, new:%d)' % (
                        self.header.channelId, header.channelId))

        if header.relative is False:
            old_header, self.header = self.header, header

            if old_header is None:
                self.manager.initialiseChannel(self)
        else:
            # this stops a circular import error
            from rtmpy.rtmp.codec.header import mergeHeaders

            self.header = mergeHeaders(self.header, header)

        self.bodyRemaining = self.header.bodyLength - self.bytes

    def _write(self, data):
        """
        If an observer is registered then L{IChannelObserver.dataReceived} is
        called, otherwise the data is buffered until an observer is
        registered.
        """
        if self.observer is not None:
            self.observer.dataReceived(data)
        else:
            if self.buffer is None:
                self.buffer = ''

            self.buffer += data

    def _adjustFrameRemaining(self, l):
        """
        Adjusts the C{frames} and C{frameRemaining} attributes based on the
        supplied length C{l}.
        """
        size = self.manager.frameSize

        while l >= size:
            self.frames += 1
            l -= size

        if l >= self.frameRemaining:
            self.frames += 1
            l -= self.frameRemaining
            self.frameRemaining = size

        self.frameRemaining -= l

    def dataReceived(self, data):
        """
        Called when a frame or partial frame is read from or written to the
        RTMP byte stream. If the 

        @param data: A string of bytes.
        @type data: C{str}
        """
        if self.header is None:
            raise HeaderError("Cannot write to a channel with no header")

        l = len(data)

        if self.bodyRemaining - l < 0:
            raise OverflowError('Attempted to write more data than was ' \
                'expected (attempted:%d remaining:%d total:%d)' % (
                    l, self.bodyRemaining, self.bytes + self.bodyRemaining))

        if DEBUG:
            log(self, 'Received %d bytes' % (l,))

        self._write(data)

        self.bytes += l
        self.bodyRemaining -= l

        self._adjustFrameRemaining(l)

    def onComplete(self):
        """
        Called when the channel has receieved the correct amount of data.
        """
        if self.manager is None:
            raise NoManagerError('A registered manager is required to ' \
                'complete a channel')

        self.manager.channelComplete(self)

        if self.observer:
            self.observer.bodyComplete()

        self.reset()

    def __repr__(self):
        s = []
        attrs = ['frameRemaining', 'frames', 'bytes', 'bodyRemaining']

        if self.header is None:
            s.append('header=None')
        else:
            s.append('channelId=%d' % (self.header.channelId,))
            s.append('datatype=%d' % (self.header.datatype,))

        for a in attrs:
            if not hasattr(self, a):
                continue

            s.append('%s=%r' % (a, getattr(self, a)))

        return '<%s.%s %s at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            ' '.join(s),
            id(self)
        )


class ChannelManager(object):
    """
    Manages the creation/deletion and general maintenance of the channels
    linked to a connected RTMP Protocol. Also handles any events that channels
    may fire.

    @ivar channels: A list of channels.
    @type channels: C{dict} of L{Channel}
    """

    implements(interfaces.IChannelManager)

    def __init__(self):
        self.channels = {}
        self.frameSize = DEFAULT_FRAME_SIZE

    def getChannel(self, channelId):
        """
        Returns a channel based on channelId. If the channel doesn't exist,
        then one is created.

        @param channelId: Index for the channel to retrieve.
        @type channelId: C{int}
        @rtype: L{Channel}
        """
        if MAX_CHANNELS < channelId < 0:
            raise IndexError("channelId is out of range (got:%d)" % (
                channelId,))

        try:
            channel = self.channels[channelId]
        except KeyError:
            if DEBUG:
                log(self, 'Creating channel %d' % (channelId,))

            channel = self.channels[channelId] = Channel()
            channel.registerManager(self)

        if DEBUG:
            log(self, 'Getting channel %r' % (channel,))

        return channel

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

    def channelComplete(self, channel):
        """
        Called when the body of the channel has been satified.
        """
        if channel.observer:
            channel.observer.bodyComplete()

        header = channel.getHeader()

        if header.datatype == 1 and header.streamId == 0:
            # change the frame size
            d = BufferedByteStream(channel.buffer)
            size = d.read_ulong()

            if DEBUG:
                log(self, 'Setting frame size to %d' % (size,))

            self.setFrameSize(int(size))

        channel.reset()

    def initialiseChannel(self, channel):
        """
        Called when a header has been applied to an inactive channel.
        """
        channel.reset()

    def setFrameSize(self, size):
        self.frameSize = size

        for channel in self.channels.values():
            channel.frameRemaining = size


class BaseProtocol(protocol.Protocol, EventDispatcher):
    """
    Provides the basis for the initial handshaking phase and decoding RTMP
    packets as they arrive.

    @ivar buffer: Contains any remaining unparsed data from the C{transport}.
    @type buffer: L{BufferedByteStream}
    @ivar state: The state of the protocol. Can be either C{HANDSHAKE} or
        C{STREAM}.
    @type state: C{str}
    """

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    def connectionMade(self):
        if DEBUG:
            log('protocol', self, "Connection made")

        protocol.Protocol.connectionMade(self)

        self.state = BaseProtocol.HANDSHAKE
        self.buffer = BufferedByteStream()
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
