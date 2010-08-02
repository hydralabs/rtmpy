"""
Handshaking specific to C{RTMP}, that is where the protocol version = C{0x03}.
"""

from rtmpy.protocol import handshake
from rtmpy import util

# from zope.interface import implements

# implements(handshake.IProtocolNegotiator)

class RandomPayloadNegotiator(object):
    """
    Functionality specific to RTMP handshaking
    """

    protocolVersion = handshake.RTMP_PROTOCOL_VERSION

    def _generate_payload(self):
        return util.generateBytes(handshake.HANDSHAKE_LENGTH - 8)

    def buildSynPayload(self):
        """
        Called to build the syn packet, based on the state of the negotiations.

        C{RTMP} payloads are just random.
        """
        return self._generate_payload()

    def buildAckPayload(self):
        """
        Called to build the ack packet, based on the state of the negotiations.

        C{RTMP} payloads are just random.
        """
        return self._generate_payload()


class ClientNegotiator(RandomPayloadNegotiator, handshake.ClientNegotiator):
    """
    A client negotiator for RTMP specific handshaking.
    """


class ServerNegotiator(RandomPayloadNegotiator, handshake.ServerNegotiator):
    """
    A server negotiator for RTMP specific handshaking.
    """


HandshakeObserver = handshake.HandshakeObserver
