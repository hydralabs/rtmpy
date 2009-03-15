# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Mock classes for testing sections of L{rtmpy.rtmp}
"""

from zope.interface import implements

from rtmpy.rtmp import interfaces

class ChannelManager(object):
    """
    Mock for L{interfaces.IChannelManager}
    """

    implements(interfaces.IChannelManager)

    def __init__(self, channels=None):
        if channels is not None:
            self.channels = channels
        else:
            self.channels = {}

        self.frameSize = 128

        self.complete = []

    def getChannel(self, id):
        try:
            return self.channels[id]
        except KeyError:
            channel = self.channels[id] = Channel(self)

        return self.channels[id]

    def channelComplete(self, channel):
        self.complete.append((channel.getHeader().channelId, channel.buffer))

        if channel.header.datatype == 1:
            from pyamf.util import BufferedByteStream
            x = BufferedByteStream(channel.buffer)
            self.frameSize = x.read_ulong()

        channel.reset()


class Channel(object):
    """
    Mock for L{interfaces.IChannel}
    """

    implements(interfaces.IChannel)

    def __init__(self, manager):
        self.registerManager(manager)
        self.reset()

    def registerManager(self, manager):
        
        self.manager = manager

    def reset(self):
        self.frameRemaining = self.manager.frameSize
        self.frames = 0
        self.bytes = 0
        self.buffer = ''
        self.consumer = None

    def write(self, data):
        l = len(data)
        self.bytes += l

        if self.consumer:
            self.consumer.write(data)
        else:
            self.buffer += str(data)

        if l < self.manager.frameSize:
            self.frameRemaining -= l

            return

        while l >= self.manager.frameSize:
            self.frames += 1
            l -= self.manager.frameSize

        if self.frameRemaining != self.manager.frameSize and \
                    l + self.frameRemaining >= self.manager.frameSize:
            self.frames += 1
            l -= self.manager.frameSize

        if l > 0:
            self.frameRemaining = l
        else:
            self.frameRemaining = self.manager.frameSize

    def setHeader(self, header):
        if header.relative is False:
            self.header = header

            return

        assert header.channelId == self.header.channelId

        # hack
        from rtmpy.rtmp.codec.header import mergeHeaders

        self.header = mergeHeaders(self.header, header)

    def getHeader(self):
        return self.header

    def bodyRemaining(self):
        return self.header.bodyLength - self.bytes

    bodyRemaining = property(bodyRemaining)

    def registerConsumer(self, consumer):
        self.consumer = consumer

        if len(self.buffer) > 0:
            self.consumer.write(self.buffer)
            self.buffer = 0


class Header(object):
    """
    A dumb object that implements L{header.IHeader}.
    """

    implements(interfaces.IHeader)

    def __init__(self, *args, **kwargs):
        self.channelId = kwargs.get('channelId', None)
        self.relative = kwargs.get('relative', None)
        self.timestamp = kwargs.get('timestamp', None)
        self.datatype = kwargs.get('datatype', None)
        self.bodyLength = kwargs.get('bodyLength', None)
        self.streamId = kwargs.get('streamId', None)


class LoopingScheduler(object):
    """
    A mock object that fake-implements L{interfaces.IChannelScheduler}.
    """

    implements(interfaces.IChannelScheduler)

    def __init__(self):
        self.activeChannels = []
        self.index = None

    def activateChannel(self, channel):
        """
        """
        self.activeChannels.append(channel)

    def deactivateChannel(self, channel):
        """
        """
        self.activeChannels.remove(channel)

    def getNextChannel(self):
        """
        """
        if len(self.activeChannels) == 0:
            return None

        if self.index is None:
            self.index = 0
        else:
            self.index += 1

        if self.index >= len(self.activeChannels):
            self.index = 0

        return self.activeChannels[self.index]