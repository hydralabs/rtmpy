# Copyright the RTMPy project
# See LICENSE.txt for details

"""
Handshaking specific to C{RTMP}.
"""

from rtmpy.protocol import handshake
from rtmpy import util

__all__ = [
    'ClientNegotiator',
    'ServerNegotiator',
]


class RandomPayloadNegotiator(object):
    """
    Generate a random payload for the syn/ack packets.
    """

    protocolVersion = version.RTMP

    def buildSynPayload(self, packet):
        """
        Called to build the syn packet, based on the state of the negotiations.

        C{RTMP} payloads are just random.
        """
        packet.payload = _generate_payload()

    def buildAckPayload(self, packet):
        """
        Called to build the ack packet, based on the state of the negotiations.

        C{RTMP} payloads are just random.
        """
        packet.payload = _generate_payload()


class ClientNegotiator(RandomPayloadNegotiator, handshake.ClientNegotiator):
    """
    A client negotiator for RTMP specific handshaking.
    """


class ServerNegotiator(RandomPayloadNegotiator, handshake.ServerNegotiator):
    """
    A server negotiator for RTMP specific handshaking.
    """


def _generate_payload():
    return util.generateBytes(handshake.HANDSHAKE_LENGTH - 8)