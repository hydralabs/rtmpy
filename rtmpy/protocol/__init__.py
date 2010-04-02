# -*- test-case-name: rtmpy.tests.test_rtmp -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is primarily used
to stream audio and video over the internet to the
U{Adobe Flash Player<http://en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be
U{AMF<http://osflash.org/documentation/amf>} or raw audio/video data like
found in U{FLV<http://osflash.org/flv>}. A single connection is capable of
multiplexing many NetStreams using different channels. Within these channels
packets are split up into fixed size body chunks.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

from twisted.internet import protocol, defer, error
from zope.interface import implements

from rtmpy.protocol import interfaces, stream, scheduler, status, event
from rtmpy import util

#: Set this to C{True} to force all rtmp.* instances to log debugging messages
DEBUG = False

#: The default RTMP port is a registered port at U{IANA<http://iana.org>}
RTMP_PORT = 1935

#: Maximum number of streams that can be active per RTMP stream
MAX_STREAMS = 0xffff


def log(obj, msg):
    """
    Used to log interesting messages from within this module (and submodules).
    """
    print repr(obj), msg


class BaseError(Exception):
    """
    Base error class for all RTMP related errors.
    """


class ErrorLoggingCodecObserver(object):
    """
    """

    def __init__(self, protocol, codec):
        self.protocol = protocol
        self.codec = codec

        self.codec.registerObserver(self)

    def started(self):
        """
        """
        self.codec.deferred.addErrback(self.protocol.logAndDisconnect)

    def stopped(self):
        """
        """


class BaseProtocol(protocol.Protocol):
    """
    Provides basic handshaking and RTMP protocol support.

    @ivar state: The state of the protocol. Can be either C{HANDSHAKE} or
        C{STREAM}.
    @type state: C{str}
    @ivar encrypted: The connection is encrypted (or requested to be
        encrypted)
    @type encrypted: C{bool}
    """

    implements(
        interfaces.IHandshakeObserver,
        interfaces.IStreamManager,
    )

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    #: This value is based on tcp dumps from FME <-> FMS 3.5
    bytesReadInterval = 1251810L

    def __init__(self):
        self.debug = DEBUG

    def buildHandshakeNegotiator(self):
        """
        Builds and returns an object that will handle the handshake phase of
        the connection.

        @raise NotImplementedError:  Must be implemented by subclasses.
        """
        raise NotImplementedError()

    def connectionMade(self):
        """
        """
        if self.debug or DEBUG:
            log(self, "Connection made")

        protocol.Protocol.connectionMade(self)

        self.encoder = None
        self.decoder = None

        self.state = BaseProtocol.HANDSHAKE
        self.handshaker = self.buildHandshakeNegotiator()

    def connectionLost(self, reason):
        """
        Called when the connection is lost for some reason.

        Cleans up any timeouts/buffer etc.
        """
        protocol.Protocol.connectionLost(self, reason)

        if self.debug or DEBUG:
            log(self, "Lost connection (reason:%s)" % str(reason))

        if self.decoder:
            self.decoder.pause()

        if self.encoder:
            self.encoder.pause()

    def decodeHandshake(self, data):
        """
        @see: U{RTMP handshake on OSFlash (external)
        <http://osflash.org/documentation/rtmp#handshake>} for more info.
        """
        self.handshaker.dataReceived(data)

    def decodeStream(self, data):
        """
        """
        self.decoder.dataReceived(data)

    def logAndDisconnect(self, failure=None):
        """
        """
        if failure is not None:
            log(self, 'error %r' % (failure,))
            log(self, failure.getBriefTraceback())

        self.transport.loseConnection()

    def dataReceived(self, data):
        """
        Called when data is received from the underlying L{transport}.
        """
        if self.state is BaseProtocol.STREAM:
            self.decodeStream(data)
        elif self.state is BaseProtocol.HANDSHAKE:
            self.decodeHandshake(data)
        else:
            self.transport.loseConnection()

            raise RuntimeError('Unknown state %r' % (self.state,))

    # interfaces.IHandshakeObserver

    def handshakeSuccess(self):
        """
        Called when the RTMP handshake was successful. Once called, packet
        streaming can commence.
        """
        from rtmpy.rtmp import codec

        if self.debug or DEBUG:
            log(self, "Successful handshake")

        self.state = self.STREAM
        self.streams = {}
        self.activeStreams = []

        self.decoder = codec.Decoder(self)
        self.encoder = codec.Encoder(self)

        ErrorLoggingCodecObserver(self, self.decoder)
        ErrorLoggingCodecObserver(self, self.encoder)

        self.encoder.registerConsumer(self.transport)

        del self.handshaker

        # TODO: slot in support for RTMPE

    def handshakeFailure(self, reason):
        """
        Called when the RTMP handshake failed for some reason. Drops the
        connection immediately.
        """
        if self.debug or DEBUG:
            log(self, "Failed handshake (reason:%s)" % str(reason))

        self.transport.loseConnection()

    def write(self, data):
        """
        """
        self.transport.write(data)

    def writePacket(self, *args, **kwargs):
        """
        """
        return self.encoder.writePacket(*args, **kwargs)

    # interfaces.IStreamManager

    def registerStream(self, streamId, stream):
        """
        """
        if streamId < 0 or streamId > MAX_STREAMS:
            raise ValueError('streamId is not in range (got:%r)' % (streamId,))

        self.streams[streamId] = stream
        self.activeStreams.append(streamId)
        stream.streamId = streamId

    def getStream(self, streamId):
        """
        """
        return self.streams[streamId]

    def removeStream(self, streamId):
        """
        Removes a stream from this connection.

        @param streamId: The id of the stream.
        @type streamId: C{int}
        @return: The stream that has been removed from the connection.
        """
        try:
            s = self.streams[streamId]
        except KeyError:
            raise IndexError('Unknown streamId %r' % (streamId,))

        del self.streams[streamId]
        self.activeStreams.remove(streamId)

        return s

    def getNextAvailableStreamId(self):
        """
        """
        if len(self.activeStreams) == MAX_STREAMS:
            return None

        self.activeStreams.sort()
        i = 0

        for j, streamId in enumerate(self.activeStreams):
            if j != i:
                return i

            i += 1

        return i

    def bytesRead(self, bytes):
        """
        """
        s = self.getStream(0)

        # XXX: hack we force the timestamp to 0 - see #55
        s.timestamp = 0

        s.writeEvent(event.BytesRead(bytes), channelId=2)


class ClientProtocol(BaseProtocol):
    """
    A very basic RTMP protocol that will act like a client.
    """

    def buildHandshakeNegotiator(self):
        """
        Generate a client handshake negotiator.

        @rtype: L{handshake.ClientNegotiator}
        """
        from rtmpy.rtmp import handshake

        return handshake.ClientNegotiator(self)

    def connectionMade(self):
        """
        Called when a connection is made to the RTMP server. Will begin
        handshake negotiations.
        """
        BaseProtocol.connectionMade(self)

        self.handshaker.start()


class ClientFactory(protocol.ClientFactory):
    """
    A helper class to provide a L{ClientProtocol} factory.
    """

    protocol = ClientProtocol
