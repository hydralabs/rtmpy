# Copyright The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake support.

@since: 0.1
"""

import sys
import time

from zope.interface import implements

from rtmpy import util, rtmp
from rtmpy.rtmp import interfaces


HANDSHAKE_LENGTH = 1536

RTMP_PROTOCOL_VERSION = 3
MAX_PROTOCOL_VERSION = 31


class HandshakeError(rtmp.BaseError):
    """
    Generic class for handshaking related errors.
    """


class ProtocolVersionError(HandshakeError):
    """
    Base error class for RTMP protocol version errors.
    """


class ProtocolTooHigh(ProtocolVersionError):
    """
    Raised if a protocol version is greater than can the requested version.
    """


class ProtocolDegraded(ProtocolVersionError):
    """
    Raised when a protocol version is lower than expected. This is a request
    from the remote endpoint to use a lower protocol version.
    """


class VerificationError(HandshakeError):
    """
    Raised if the handshake verification failed.
    """


class BaseToken(object):
    """
    Base functionality for handshake tokens. This is a state object for the
    negotiators.

    @ivar uptime: The number of milliseconds since an arbitrary epoch. This is
        generally the uptime of the machine.
    @type uptime: 32bit unsigned int.
    @ivar version: The api version for the handshake. This is used for check
        for H.264 support. On encoding this will be a 32bit unsigned int.
    @type version: C{int} or L{versions.Version}
    """

    first = None
    second = None
    payload = None
    timestamp = None

    def __init__(self, **kwargs):
        kwargs.setdefault('timestamp', int(time.time()))

        self.__dict__.update(kwargs)

    def encode(self, buffer):
        buffer.write_ulong(self.first or 0)
        buffer.write_ulong(self.second or 0)

        payload = self.encodePayload()

        if payload:
            buffer.write(payload)

    def decode(self, buffer):
        self.first = buffer.read_ulong()
        self.second = buffer.read_ulong()

        self.decodePayload(buffer)

    def encodePayload(self):
        raise NotImplementedError

    def decodePayload(self, buffer):
        self.payload = buffer.read(HANDSHAKE_LENGTH - 8)


class RandomPayloadToken(BaseToken):
    """
    A token that provides a simple C{payload} attribute which will contain an
    arbitrary block of data used to identify the token.

    This is the token type used for RTMP handshakes. The idea in the future is
    that RTMPE/T/S/FP(!) implementations will have their own tokens as required.
    """

    def encodePayload(self):
        """
        Generate some random data.
        """
        if self.payload:
            return self.payload

        self.payload = util.generateBytes(HANDSHAKE_LENGTH - 8)

        return self.payload


class BaseNegotiator(object):
    """
    Abstract functionality for negotiating an RTMP handshake.

    @ivar observer: An observer for handshake negotiations.
    @type observer: L{IHandshakeObserver}
    @ivar buffer: Any data that has not yet been consumed.
    """

    implements(interfaces.IHandshakeNegotiator)

    protocolVersion = RTMP_PROTOCOL_VERSION
    token_class = RandomPayloadToken

    def __init__(self, observer):
        self.observer = observer
        self.started = False

    def start(self, uptime, version):
        """
        Called to start the handshaking negotiations. Writes the header byte
        and client payload to the observer.
        """
        if self.started:
            raise HandshakeError('Handshake negotiator cannot be restarted')

        self.started = True
        self.buffer = util.BufferedByteStream()

        self.peer_version = None

        self.my_syn = self.token_class(first=uptime, second=version)
        self.my_ack = None

        self.peer_syn = None
        self.peer_ack = None

    def versionReceived(self):
        if self.peer_version == self.protocolVersion:
            return

        if self.peer_version > MAX_PROTOCOL_VERSION:
            raise ProtocolVersionError('Invalid protocol version')

        if self.peer_version > self.protocolVersion:
            raise ProtocolTooHigh('Unexpected protocol version')

    def getPeerToken(self):
        if self.buffer.remaining() < HANDSHAKE_LENGTH:
            # we're expecting more data
            return

        token = self.token_class()

        token.decode(self.buffer)

        return token

    def writeVersionAndSyn(self):
        self.buffer.truncate()
        self.buffer.write_uchar(self.protocolVersion)

        self.writeToken(self.my_syn)

    def writeToken(self, token):
        token.encode(self.buffer)

        data = self.buffer.getvalue()
        self.buffer.truncate()

        self.observer.write(data)

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{self.observer.handshakeFailure}
        must be called, citing the reason.
        """
        try:
            if not self.started:
                raise HandshakeError('Data was received, but negotiator was '
                    'not started')

            self.buffer.append(data)

            if not self.peer_version:
                if self.buffer.remaining() < 1:
                    # we're expecting more data
                    return

                self.peer_version = self.buffer.read_uchar()

                self.versionReceived()

            self.process()
        except:
            self.observer.handshakeFailure(*sys.exc_info())

    def process(self):
        raise NotImplementedError


class ClientNegotiator(BaseNegotiator):
    """
    Negotiator for client initiating handshakes.
    """

    def start(self, uptime, version):
        """
        Called to start the handshaking negotiations. Writes the protocol
        version and initial payload to the observer.
        """
        BaseNegotiator.start(self, uptime, version)

        self.writeVersionAndSyn()

    def versionReceived(self):
        BaseNegotiator.versionReceived(self)

        if self.peer_version < self.protocolVersion:
            raise ProtocolDegraded('Protocol version did not match '
                '(got %d, expected %d)' % (
                    self.peer_version, self.protocolVersion))

    def process(self):
        if not self.peer_syn:
            self.peer_syn = self.getPeerToken()

            if not self.peer_syn:
                return

        if not self.peer_ack:
            self.peer_ack = self.getPeerToken()

            if not self.peer_ack:
                return

        if self.buffer.remaining() != 0:
            raise HandshakeError('Unexpected trailing data after peer syn/ack')

        if self.peer_ack.first != self.my_syn.first:
            raise VerificationError('Received uptime is not the same')

        if self.peer_ack.payload != self.my_syn.payload:
            raise VerificationError('Received payload is not the same')

        self.my_ack = self.token_class(first=self.peer_syn.first,
            second=self.peer_syn.timestamp)

        self.buffer.truncate()
        self.writeToken(self.my_ack)

        # if we get here then a successful handshake has been negotiated.
        # inform the observer accordingly
        self.observer.handshakeSuccess()


class ServerNegotiator(BaseNegotiator):
    """
    Negotiator for server handshakes.
    """

    def versionReceived(self):
        BaseNegotiator.versionReceived(self)

        self.writeVersionAndSyn()

    def process(self):
        if not self.peer_syn:
            self.peer_syn = self.getPeerToken()

            if not self.peer_syn:
                return

            self.my_ack = self.token_class(first=self.peer_syn.timestamp,
                second=self.my_syn.timestamp)

            self.buffer.truncate()
            self.writeToken(self.my_ack)

        if not self.peer_ack:
            self.peer_ack = self.getPeerToken()

            if not self.peer_ack:
                return

        if self.my_syn.first != self.peer_ack.first:
            raise VerificationError('Received uptime is not the same')

        if self.my_syn.payload != self.peer_ack.payload:
            raise VerificationError('Received payload does not match')

        # at this point, as far as the server is concerned, handshaking has
        # been successful

        self.observer.handshakeSuccess()
