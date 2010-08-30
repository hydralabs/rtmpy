# -*- test-case-name: rtmpy.tests.test_rtmp -*-
# Copyright The RTMPy Project
# See LICENSE for details

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is primarily used
to stream audio and video over the internet to the U{Adobe Flash Player<http://
en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be
U{AMF<http://osflash.org/documentation/amf>} or raw audio/video data like
found in U{FLV<http://osflash.org/flv>}. A single connection is capable of
multiplexing many NetStreams using different channels. Within these channels
packets are split up into fixed size body chunks.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

from twisted.internet import protocol
from zope.interface import implements

from rtmpy.protocol import interfaces, stream, status
from rtmpy import util
from rtmpy.protocol import handshake

#: Set this to C{True} to force all rtmp.* instances to log debugging messages
DEBUG = False

#: The default RTMP port is a registered port at U{IANA<http://iana.org>}
RTMP_PORT = 1935

RTMP_PROTOCOL_VERSION = 3
RTMPE_PROTOCOL_VERSION = 6
MAX_PROTOCOL_VERSION = 31

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


class VersionMismatch(BaseError):
    """
    """

    def __init__(self, versionReceived, *args, **kwargs):
        BaseError.__init__(self, *args, **kwargs)

        self.version = versionReceived


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
        interfaces.IStreamManager,
    )

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    #: This value is based on tcp dumps from FME <-> FMS 3.5
    bytesReadInterval = 1251810L

    def __init__(self):
        self.debug = DEBUG

    def connectionMade(self):
        """
        """
        self.state = BaseProtocol.HANDSHAKE

        self.handshaker = self.factory.buildHandshakeNegotiator(self)

        self.handshaker.start(0, 0)

    def decodeStream(self, data):
        """
        """
        self.decoder.dataReceived(data)

    def dataReceived(self, data):
        """
        Called when data is received from the underlying L{transport}.
        """
        dr = getattr(self, '_' + self.state + '_dataReceived', None)

        try:
            dr(data)
        except:
            self.transport.loseConnection()

            raise

    def _stream_dataReceived(self, data):
        print 'eh', repr(data)

    def _handshake_dataReceived(self, data):
        self.handshaker.dataReceived(data)

    # interfaces.IHandshakeObserver

    def handshakeSuccess(self, data):
        """
        Called when the RTMP handshake was successful. Once called, packet
        streaming can commence.
        """
        self.state = self.STREAM

        del self.handshaker

        if data:
            self.dataReceived(data)

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
