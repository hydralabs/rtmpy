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

from twisted.internet import protocol, defer
from zope.interface import implements
from odict import odict

from rtmpy.rtmp import interfaces, stream, scheduler
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

    implements(interfaces.IHandshakeObserver)

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

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
        if self.debug or DEBUG:
            log(self, "Connection made")

        protocol.Protocol.connectionMade(self)

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
        self.decoder.dataReceived(data)

        if self.decoder.deferred is None:
            self.decoder.start().addErrback(self.logAndDisconnect)

    def logAndDisconnect(self, failure=None):
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

        self.decoder = codec.Decoder(self)
        self.encoder = codec.Encoder(self)

        # we only need to register for events on the decoder - the encoder
        # takes care of itself (at least so far)
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

    def codecStarted(self, d):
        """
        """
        d.addErrback(self.logAndDisconnect)

    def writePacket(self, *args, **kwargs):
        d = self.encoder.writePacket(*args, **kwargs)

        self.encoder.start()

        return d

    # interfaces.IStreamManager

    def registerStream(self, streamId, stream):
        """
        """
        self.streams[streamId] = stream
        stream.streamId = streamId

    def getStream(self, streamId):
        """
        """
        return self.streams[streamId]


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


class ServerProtocol(BaseProtocol):
    """
    A very basic RTMP protocol that will act like a server.
    """

    def buildHandshakeNegotiator(self):
        """
        Generate a server handshake negotiator.

        @rtype: L{handshake.ServerNegotiator}
        """
        from rtmpy.rtmp import handshake

        return handshake.ServerNegotiator(self)

    def connectionMade(self):
        """
        Called when a connection is made to the RTMP server. Will begin
        handshake negotiations.
        """
        BaseProtocol.connectionMade(self)

        self.handshaker.start(version=0)

    def handshakeSuccess(self):
        """
        Called when the handshake has been successfully negotiated. If there
        is any data in the negotiator buffer it will be re-inserted into the
        main RTMP stream (as any data after the handshake must be RTMP).
        """
        b = self.handshaker.buffer

        BaseProtocol.handshakeSuccess(self)

        self.encoder.registerScheduler(scheduler.LoopingChannelScheduler())

        self.registerStream(0, stream.ServerControlStream(self))
        self.client = None

        if len(b) > 0:
            self.dataReceived(b)

    def onConnect(self, *args):
        """
        Called when a 'connect' packet is received from the endpoint.
        """
        stream = self.getStream(0)
        r = defer.Deferred()

        def cb(res):
            print 'sending response'
            # connection always succeeds
            r.callback((
                odict([('capabilities', 31), ('fmsVer', u'FMS/3,0,1,123')]),
                odict([('code', u'NetConnection.Connect.Success'), ('objectEncoding', 0), ('description', u'Connection succeeded.'), ('level', u'status')])
            ))

        def writeClientBW(res):
            print 'writing client bw'
            d = stream.writeEvent(event.ClientBandwidth(2500000L, 2), channelId=2)

            d.addCallback(cb)

        d = stream.writeEvent(event.ServerBandwidth(2500000L), channelId=2)
        d.addCallback(writeClientBW)

        return r


class ServerFactory(protocol.Factory):
    """
    A helper class to provide a L{ServerProtocol} factory.
    """

    protocol = ServerProtocol
