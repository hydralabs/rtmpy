# -*- test-case-name: rtmpy.tests.rtmp.test_stream -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Stream implementation.

@since: 0.1
"""

from zope.interface import implements
from twisted.internet import defer

from rtmpy.rtmp import interfaces, event


class BufferingChannelObserver(object):
    """
    """

    def __init__(self, stream, channel):
        self.stream = stream
        self.channel = channel
        self.buffer = ''

    def dataReceived(self, data):
        self.buffer += data

    def bodyComplete(self):
        self.stream.eventReceived(self.channel, self.buffer)

    def headerChanged(self, header):
        if header.timestamp is not None:
            self.stream.timestamp = header.timestamp


class StreamingChannelObserver(object):
    """
    """

    def __init__(self, stream, channel):
        self.stream = stream
        self.channel = channel

    def dataReceived(self, data):
        self.stream.dataReceived(self.channel, data)

    def bodyComplete(self):
        self.stream.channelComplete(self.channel)


class ControlStream(object):
    """
    """

    def __init__(self, protocol):
        self.protocol = protocol
        self.decodingChannels = {}
        #: a list of channels that are encoding stuff
        self.encodingChannels = {}
        self.timestamp = 0

    def registerChannel(self, channelId):
        """
        """
        channel = self.protocol.encoder.getChannel(channelId)
        self.encodingChannels[channelId] = channel

        return channel

    def channelRegistered(self, channel):
        """
        """
        header = channel.getHeader()
        kls = event.get_type_class(header.datatype)

        if interfaces.IStreamable.providedBy(kls):
            channel.registerObserver(StreamingChannelObserver(self, channel))
        else:
            channel.registerObserver(BufferingChannelObserver(self, channel))

        self.decodingChannels[header.channelId] = channel

    def channelUnregistered(self, channel):
        """
        """
        header = channel.getHeader()

        del self.decodingChannels[header.channelId]

    def dispatchEvent(self, e, channel):
        """
        """
        def cb(res):
            if not interfaces.IEvent.providedBy(res):
                return res

            header = channel.getHeader()
            self.writeEvent(res, header.channelId)

        d = defer.maybeDeferred(e.dispatch, self).addCallback(cb)

    def eventReceived(self, channel, data):
        """
        """
        header = channel.getHeader()
        kls = event.get_type_class(header.datatype)

        d = event.decode(header.datatype, data)

        d.addErrback(self.protocol.logAndDisconnect)
        d.addCallback(self.dispatchEvent, channel)

    # interfaces.IStreamWriter

    def writeEvent(self, e, channelId=None):
        """
        """
        def cb(res, channelId):
            channel = None

            if channelId is None:
                channelId = self.protocol.encoder.getNextAvailableChannelId()
            else:
                try:
                    channel = self.encodingChannels[channelId]
                except KeyError:
                    pass

            if channel is None:
                channel = self.registerChannel(channelId)

            return self.protocol.writePacket(self.streamId, channelId, res[0], res[1], self.timestamp)

        return event.encode(e).addCallback(cb, channelId)

    # interfaces.IEventListener

    def onInvoke(self, invoke):
        """
        """
        pass


class ServerControlStream(ControlStream):
    """
    """

    def onInvoke(self, invoke):
        """
        """
        def cb(res):
            return event.Invoke('_result', invoke.id, *res)

        if invoke.name == u'connect':
            d = defer.maybeDeferred(self.protocol.onConnect, *invoke.argv)
            d.addCallback(cb)

            return d
