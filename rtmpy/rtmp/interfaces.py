# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Interface documentation.
"""

from twisted.internet import interfaces
from zope.interface import Interface, Attribute, implements


class IHeader(Interface):
    """
    An RTMP Header.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    relative = Attribute(
        "A C{bool} which is C{True} if this header is relative to the "
        "previous. If C{False} then the header completely replaces the "
        "previous. If this value is C{False} then all other attributes on "
        "the header are guaranteed to be populated.")
    timestamp = Attribute(
        "An C{int} time value - not sure what this represents atm.")
    datatype = Attribute(
        "The datatype for the corresponding channel. See "
        "L{http://osflash.org/documentation/rtmp#rtmp_datatypes} for a list "
        "of possibles.")
    bodyLength = Attribute(
        "An C{int} which represents the length of the channel body.")
    streamId = Attribute(
        "An C{int} representing the linked stream.")


class IChannel(Interface):
    """
    An RTMP channel. A channel acts as an intermediary between two endpoints, 
    as well as providing context information for protocol en/decoding.
    """

    bytes = Attribute(
        "The total number of bytes that have been routed through this "
        "channel.")
    frames = Attribute(
        "The total number of frames that have been routed through this "
        "channel.")
    bodyRemaining = Attribute(
        "The number of bytes that remain until this channel's body is "
        "considered complete.")

    def registerManager(manager):
        """
        Registers a channel manager.

        @param manager: L{IChannelManager}
        @raise TypeError: If manager does not provide L{IChannelManager}
        """

    def registerConsumer(consumer):
        """
        Registers a consumer for this channel.
        """

    def getHeader():
        """
        Returns the last header read from/written to the stream. Returns
        C{None} if no header was applied to this channel

        @rtype: L{IHeader} or C{None}.
        """

    def setHeader(header):
        """
        Sets the header for this channel. If the header is relative, then it
        is 'merged' with the last absolute header.

        @type header: L{IHeader}
        """

    def write(data):
        """
        """


class IChannelManager(Interface):
    """
    Defines the interface for managing channels. The channel manager handles
    the interactions between its registered channels and the outside world ..
    """

    frameSize = Attribute("An C{int} that defines the size (in bytes) of "
        "each frame body.")

    def getChannel(channelId):
        """
        Returns a L{IChannel} object based on the channeId.

        @raise IndexError: C{channelId} is not in range.
        @rtype: L{IChannel}
        """

    def getNextAvailableChannelId():
        """
        Returns the next available channel id.

        @rtype: C{int}
        @raise OverflowError: There are no free channels.
        """

    def getLastHeader(channelId):
        """
        Returns the last header for a channelId.

        @type channelId: C{int}
        @raise IndexError: The channel isn't registered to this manager.
        @raise IndexError: The channelId is out of range.
        @rtype: L{IHeader} or C{None}
        """


class IChannelScheduler(Interface):
    """
    A channel scheduler is meant to iteratively supply 'active' channels via
    the L{getNextChannel} method.
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
