# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Utility classes for testing.
"""

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

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
