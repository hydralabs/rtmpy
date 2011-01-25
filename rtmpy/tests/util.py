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
Utility classes for testing.
"""

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
    
try:
    unicode
except NameError:
    unicode = str

from twisted.internet import error


class StringTransport:
    disconnecting = 0

    hostAddr = None
    peerAddr = None

    def __init__(self, hostAddress=None, peerAddress=None):
        self.clear()
        if hostAddress is not None:
            self.hostAddr = hostAddress
        if peerAddress is not None:
            self.peerAddr = peerAddress
        self.connected = True

    def clear(self):
        self.io = StringIO()

    def value(self):
        return self.io.getvalue()

    def write(self, data):
        if isinstance(data, unicode): # no, really, I mean it
            raise TypeError("Data must not be unicode")
        self.io.write(data)

    def writeSequence(self, data):
        self.io.write(''.join(data))

    def loseConnection(self):
        pass

    def getPeer(self):
        if self.peerAddr is None:
            return ('StringIO', repr(self.io))
        return self.peerAddr

    def getHost(self):
        if self.hostAddr is None:
            return ('StringIO', repr(self.io))
        return self.hostAddr


class StringTransportWithDisconnection(StringTransport):
    def loseConnection(self):
        if self.connected:
            self.connected = False
            self.protocol.connectionLost(error.ConnectionDone("Bye."))


class DummyDelayedCall:
    cancelled = False

    def cancel(self):
        self.cancelled = True
    