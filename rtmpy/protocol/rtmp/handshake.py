# Copyright The RTMPy Project
# See LICENSE.txt for details

"""
Handshaking specific to C{RTMP}.
"""

from rtmpy.protocol import handshake, rtmp
from rtmpy import util

__all__ = [
    'ClientNegotiator',
    'ServerNegotiator',
    'HandshakeObserver'
]


class RandomPayloadNegotiator(object):
    """
    Generate a random payload for the syn/ack packets.
    """

    protocolVersion = rtmp.PROTOCOL_VERSION

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
