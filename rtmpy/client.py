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
RTMP client implementation.

@since: 0.1.0
"""

from zope.interface import implements
from twisted.internet import reactor, protocol as twisted_protocol
import twisted

from rtmpy import protocol, util, versions
from rtmpy.protocol import handshake


class ClientProtocol(protocol.BaseProtocol):
    """
    Client RTMP Protocol.
    """

    version = versions.FLASH_MIN_H264
    protocolVersion = protocol.RTMP_PROTOCOL_VERSION

    def connectionMade(self):
        """
        Called when a connection has been made to this protocol instance. Used
        to do general setup and protocol initialisation.
        """
        rtmp.BaseProtocol.connectionMade(self)

        self.negotiator = self.factory.getHandshakeNegotiator(self, self.protocolVersion)

        self.negotiator.start(0, self.version)

    def connectionLost(self, *args):
        print args


class ClientFactory(twisted_protocol.ClientFactory):
    """
    RTMP client protocol factory.
    """

    protocol = ClientProtocol

    def getHandshakeNegotiator(self, protocol, version):
        """
        Returns an implementation of L{handshake.IHandshakeNegotiator} based on
        the version supplied.

        @param protocol: The client protocol instance.
        @type protocol: L{ClientProtocol}
        @param version: The RTMP version request.
        @type version: C{int}
        """
        imp = handshake.get_implementation(version)

        return imp.ClientNegotiator(imp.HandshakeObserver(protocol))
