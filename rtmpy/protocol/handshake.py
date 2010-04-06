# Copyright The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake support.

@since: 0.1
"""

import sys
import time

from zope.interface import implements

from rtmpy import util, protocol
from rtmpy.protocol import interfaces


HANDSHAKE_LENGTH = 1536

RTMP_PROTOCOL_VERSION = 3
MAX_PROTOCOL_VERSION = 31


class HandshakeError(protocol.BaseError):
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


class Token(object):
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
        timestamp = kwargs.get('timestamp', None)

        if not timestamp:
            kwargs['timestamp'] = int(time.time())

        self.__dict__.update(kwargs)

    def encode(self, buffer):
        buffer.write_ulong(self.first or 0)
        buffer.write_ulong(self.second or 0)

        buffer.write(self.payload)

    def decode(self, buffer):
        self.first = buffer.read_ulong()
        self.second = buffer.read_ulong()

        self.payload = buffer.read(HANDSHAKE_LENGTH - 8)


class BaseNegotiator(object):
    """
    Abstract functionality for negotiating an RTMP handshake.

    @ivar observer: An observer for handshake negotiations.
    @type observer: L{IHandshakeObserver}
    @ivar buffer: Any data that has not yet been consumed.
    """

    implements(interfaces.IHandshakeNegotiator)

    protocolVersion = RTMP_PROTOCOL_VERSION

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

        self.my_syn = Token(first=uptime, second=version)
        self.my_ack = None

        self.peer_syn = None
        self.peer_ack = None

    def getPeerToken(self):
        if self.buffer.remaining() < HANDSHAKE_LENGTH:
            # we're expecting more data
            return

        token = Token()

        token.decode(self.buffer)

        return token

    def writeVersionAndSyn(self):
        self.buffer.truncate()
        self.buffer.write_uchar(self.protocolVersion)

        self._writeToken(self.my_syn)

    def _writeToken(self, token):
        token.encode(self.buffer)

        data = self.buffer.getvalue()
        self.buffer.truncate()

        self.observer.write(data)

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{self.observer.handshakeFailure}
        will be called, citing the reason.
        """
        try:
            if not self.started:
                raise HandshakeError('Data was received, but negotiator was '
                    'not started')

            self.buffer.append(data)

            self._process()
        except:
            self.observer.handshakeFailure(*sys.exc_info())

    def _process(self):
        if not self.peer_version:
            if self.buffer.remaining() < 1:
                # we're expecting more data
                return

            self.peer_version = self.buffer.read_uchar()

            self.versionReceived()

        if not self.peer_syn:
            self.peer_syn = self.getPeerToken()

            if not self.peer_syn:
                return

            self.synReceived()

        if not self.peer_ack:
            self.peer_ack = self.getPeerToken()

            if not self.peer_ack:
                return

            self.ackReceived()

        # if we get here then a successful handshake has been negotiated.
        # inform the observer accordingly
        self.observer.handshakeSuccess()

    def writeAck(self):
        self.buildAckPayload(self.my_ack)

        self.buffer.truncate()
        self._writeToken(self.my_ack)

    def buildSynPayload(self, token):
        """
        """
        generate_payload(token)

    def buildAckPayload(self, token):
        """
        """
        generate_payload(token)

    def versionReceived(self):
        if self.peer_version == self.protocolVersion:
            return

        if self.peer_version > MAX_PROTOCOL_VERSION:
            raise ProtocolVersionError('Invalid protocol version')

        if self.peer_version > self.protocolVersion:
            raise ProtocolTooHigh('Unexpected protocol version')

    def synReceived(self):
        """
        """

    def ackReceived(self):
        """
        """


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

        self.buildSynPayload(self.my_syn)

        self.writeVersionAndSyn()

    def versionReceived(self):
        BaseNegotiator.versionReceived(self)

        if self.peer_version < self.protocolVersion:
            raise ProtocolDegraded('Protocol version did not match (got %d, '
                'expected %d)' % (self.peer_version, self.protocolVersion))

    def synReceived(self):
        pass

    def ackReceived(self):
        if self.buffer.remaining() != 0:
            raise HandshakeError('Unexpected trailing data after peer ack')

        if self.peer_ack.first != self.my_syn.first:
            raise VerificationError('Received uptime is not the same')

        if self.peer_ack.payload != self.my_syn.payload:
            raise VerificationError('Received payload is not the same')

        self.my_ack = Token(first=self.peer_syn.first, second=self.my_syn.timestamp)

        self.writeAck()


class ServerNegotiator(BaseNegotiator):
    """
    Negotiator for server handshakes.
    """

    def versionReceived(self):
        BaseNegotiator.versionReceived(self)

        self.buildSynPayload(self.my_syn)

        self.writeVersionAndSyn()

    def synReceived(self):
        self.my_ack = Token(first=self.peer_syn.timestamp, second=self.my_syn.timestamp)

        self.writeAck()

    def ackReceived(self):
        if self.my_syn.first != self.peer_ack.first:
            raise VerificationError('Received uptime is not the same')

        if self.my_syn.payload != self.peer_ack.payload:
            raise VerificationError('Received payload does not match')


def generate_payload(token):
    token.payload = util.generateBytes(HANDSHAKE_LENGTH - 8)
