# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Utility classes for testing.
"""

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from twisted.internet import error
from rtmpy.rtmp import interfaces
from zope.interface import implements


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


class DummyChannelManager(object):
    """
    """

    implements(interfaces.IChannelManager)

    def __init__(self, channels=None):
        if channels is not None:
            self.channels = channels
        else:
            self.channels = {}

    def getChannel(self, id):
        try:
            return self.channels[id]
        except KeyError:
            self.channels[id] = DummyChannel()

        return self.channels[id]


class DummyChannel(object):
    """
    """

    implements(interfaces.IChannel)

    frameSize = 128

    def __init__(self):
        self.frameRemaining = self.frameSize
        self.frames = 0
        self.buffer = ''

    def write(self, data):
        self.buffer += str(data)

        l = len(data)

        if l < self.frameSize:
            self.frameRemaining -= l

            return

        while l >= self.frameSize:
            self.frames += 1
            l -= self.frameSize

        if self.frameRemaining != self.frameSize and l + self.frameRemaining >= self.frameSize:
            self.frames += 1
            l -= self.frameSize

        if l > 0:
            self.frameRemaining = l
        else:
            self.frameRemaining = self.frameSize

    def setHeader(self, header):
        if header.relative is False:
            self.header = header

            return

        assert header.channelId == self.header.channelId

        # hack
        from rtmpy.rtmp.codec.header import mergeHeaders

        self.header = mergeHeaders(self.header, header)

    def bodyRemaining(self):
        return self.header.bodyLength - len(self.buffer)

    bodyRemaining = property(bodyRemaining)


class DummyHeader(object):
    """
    A dumb object that implements L{header.IHeader}
    """

    implements(interfaces.IHeader)

    def __init__(self, *args, **kwargs):
        self.channelId = kwargs.get('channelId', None)
        self.relative = kwargs.get('relative', None)
        self.timestamp = kwargs.get('timestamp', None)
        self.datatype = kwargs.get('datatype', None)
        self.bodyLength = kwargs.get('bodyLength', None)
        self.streamId = kwargs.get('streamId', None)
