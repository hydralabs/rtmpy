# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
Handshaking specific to C{RTMP}.
"""

from rtmpy.protocol import handshake, version
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
