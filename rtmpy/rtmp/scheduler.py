# -*- test-case-name: rtmpy.tests.test_scheduler -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Contains various implementations for scheduling RTMP channels for encoding.

@since: 0.1
"""

from zope.interface import implements

from rtmpy.rtmp import interfaces


class BaseChannelScheduler(object):
    """
    Base functionality for all schedulers.

    @ivar activeChannels: A C{dict} of channels that are actively producing
        data. Deactivated channels are listed as C{None}, for easy looping.
    @type activeChannels: C{dict}
    """

    implements(interfaces.IChannelScheduler)

    def __init__(self):
        self.activeChannels = []

    def activateChannel(self, channel):
        """
        Activates a channel for scheduling.

        @param channel: The channel to activate.
        @type channel: L{interfaces.IChannel}
        """
        if channel in self.activeChannels:
            raise IndexError('channel already activated')

        self.activeChannels.append(channel)

    def deactivateChannel(self, channel):
        """
        Deactivates a channel from scheduling.

        @param channel: The channel to activate.
        @type channel: L{interfaces.IChannel}
        """
        try:
            idx = self.activeChannels.index(channel)
        except ValueError:
            raise IndexError('channel not activated')

        self.activeChannels[idx] = None

    def getNextChannel(self):
        """
        Must be provided by the implementing concrete class.
        """
        raise NotImplementedError


class LoopingChannelScheduler(BaseChannelScheduler):
    """
    A simple scheduler that continuously loops over the active channels not
    giving priority to any one.

    @ivar index: The current index of C{activeChannels}.
    @type index: C{int}
    """

    def __init__(self):
        BaseChannelScheduler.__init__(self)

        self.index = None
        self._len = 0

    def activateChannel(self, channel):
        BaseChannelScheduler.activateChannel(self, channel)

        self._len += 1

    def _incrementIndex(self):
        if self.index is None:
            self.index = 0

            return

        self.index += 1

        if self.index >= self._len:
            self.index = 0

    def getNextChannel(self):
        """
        Loops over C{activeChannels}.

        @return: The next active channel.
        @rtype: L{implements.IChannel} or C{None}.
        """
        if self._len == 0:
            return None

        self._incrementIndex()

        channel = self.activeChannels[self.index]
        i = self.index

        while channel is None:
            self._incrementIndex()

            if self.index == i:
                break

            channel = self.activeChannels[self.index]

        if channel is None:
            self.activeChannels = []
            self._len = 0

        return channel
