# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Interface documentation for RTMP primitives.

@since: 0.1
"""

from zope.interface import Interface, Attribute


class IChannelScheduler(Interface):
    """
    A channel scheduler is meant to iteratively supply 'active' channels via
    the L{getNextChannel} method. Used for RTMP encoding.
    """

    def activateChannel(channel):
        """
        Activates a channel for scheduling.

        @param channel: The channel to activate.
        @type channel: L{IChannel}
        """

    def deactivateChannel(channel):
        """
        Deactivates a channel for scheduling.

        @param channel: The channel to deactivate.
        @type channel: L{IChannel}
        """

    def getNextChannel():
        """
        Returns the next active channel. The definition of 'next' is up to the
        implementing class. If there are no more active channels then C{None}
        should be returned.
        """


class ICodec(Interface):
    """
    """

    deferred = Attribute("")

    def getJob(self):
        """
        """

    def start(when):
        """
        """

    def pause():
        """
        """

    def registerObserver(observer):
        """

        @type observer: L{ICodecObserver}
        """


class ICodecObserver(Interface):
    """
    Observes RTMP codec events.
    """

    def started():
        """
        Called when the codec has re/started.
        """

    def stopped():
        """
        Called when encoding has paused.
        """


class IConsumingStream(Interface):
    """
    Deals with part of a stream that linked with decoding RTMP events.
    """

    def channelRegistered(channel):
        """
        Called when a channel has registered itself to this stream.

        @type channel: L{IChannel}
        """

    def channelUnregistered(channel):
        """
        Called when a channel has unregistered itself from this channel

        @type channel: L{IChannel}
        """

    def dispatchEvent(event, channel):
        """
        Called to dispatch an event to the stream.

        @type event: L{IEvent}
        @param channel: The channel that the event was generated from.
        @type channel: L{IChannel}
        """


class IProducingStream(Interface):
    """
    Deals with part of a stream that linked with encoding RTMP events.
    """

    def registerChannel(channel):
        """
        Called to register a channel to this stream.

        @type channel: L{IChannel}
        """

    def unregisterChannel(channel):
        """
        Called to unregister a channel from this stream.

        @type channel: L{IChannel}
        """

    def writeEvent(event, channel=None):
        """
        Write an event to the stream. If channel is C{None} then one will be
        allocated.

        @type event: L{IEvent}
        @param channel: The channel that the event was generated from.
        @type channel: L{IChannel}
        """



class IStreamManager(Interface):
    """
    A manager that handles RTMP streams.
    """

    def registerStream(streamId, stream):
        """
        Registers a L{IStream} instance to the manager, based on the C{streamId}.

        @param streamId: The id used to identify the stream to the manager.
        @type streamId: C{int}
        @param stream: The stream instance.
        @type stream: L{interfaces.IStream}
        @raise ValueError: C{streamId} is not in the correct range.
        @raise TypeError: C{stream} does not implement L{interfaces.IStream}.
        @raise IndexError: C{streamId} is already registered to another stream.
        """

    def removeStream(streamId):
        """
        Removes the stream from this manager.

        @param streamId: The id used to identify the stream to the manager.
        @type streamId: C{int}
        @return: The stream object that has been removed.
        @rtype: L{IStream}
        @raise ValueError: C{streamId} is not in the correct range.
        @raise IndexError: C{streamId} does not have a stream registered to it.
        """

    def getStream(streamId):
        """
        """
