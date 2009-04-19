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
from twisted.internet.interfaces import ITransport
from zope.interface import implements
from pyamf.util import IndexedCollection, BufferedByteStream

from rtmpy.rtmp import interfaces
from rtmpy.rtmp import log


#: The default RTMP port is a registered at U{IANA<http://iana.org>}.
RTMP_PORT = 1935

MAX_STREAMS = 0xffff

DEBUG = False


def log(obj, msg):
    """
    Used to log interesting messages from within this module (and submodules).
    """
    print repr(obj), msg


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
        self.encrypted = False
        self.debug = DEBUG

    def buildHandshakeNegotiator(self):
        """
        """
        raise NotImplementedError

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
        if self.debug or DEBUG:
            log(self, "Lost connection (reason:%s)" % str(reason))

        if hasattr(self, 'decoder'):
            self.decoder.pause()

        if hasattr(self, 'encoder'):
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
        if self.debug or DEBUG:
            log(self, 'error %r' % (failure,))

        self.transport.loseConnection()

    def dataReceived(self, data):
        """
        Called when data is received from the underlying transport.
        """
        if self.state is BaseProtocol.STREAM:
            self.decodeStream(data)
        elif self.state is BaseProtocol.HANDSHAKE:
            self.decodeHandshake(data)

    # interfaces.IHandshakeObserver

    def handshakeSuccess(self):
        """
        Called when the RTMP handshake was successful. Once this is called,
        packet streaming can commence.
        """
        from rtmpy.rtmp import codec

        if self.debug or DEBUG:
            log(self, "Successful handshake")

        self.state = self.STREAM

        self.decoder = codec.Decoder(self)
        self.encoder = codec.Encoder(self)

        self.encoder.registerConsumer(self.transport)

        # TODO slot in support for RTMPE

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


class ClientProtocol(BaseProtocol):
    """
    A client woot!
    """

    def buildHandshakeNegotiator(self):
        """
        """
        from rtmpy.rtmp import handshake

        return handshake.ClientNegotiator(self)

    def connectionMade(self):
        """
        """
        BaseProtocol.connectionMade(self)

        self.handshaker.start(version=0)


class ClientFactory(protocol.ClientFactory):
    """
    """

    protocol = ClientProtocol


class ServerProtocol(BaseProtocol):
    """
    A server woot!
    """

    def buildHandshakeNegotiator(self):
        """
        """
        from rtmpy.rtmp import handshake

        return handshake.ServerNegotiator(self)

    def connectionMade(self):
        """
        """
        BaseProtocol.connectionMade(self)

        self.handshaker.start(version=0)


class ServerFactory(protocol.Factory):
    """
    """

    protocol = ServerProtocol
