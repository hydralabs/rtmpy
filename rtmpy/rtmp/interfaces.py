# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Interface documentation.

@since: 0.1
"""

from twisted.internet import interfaces
from zope.interface import Interface, Attribute, implements

# First the basic components of RTMP bytestreams.

class IHeader(Interface):
    """
    An RTMP Header.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    relative = Attribute(
        "A C{bool} which is C{True} if this header is relative to the "
        "previous. If C{False} then the header completely replaces the "
        "previous.")
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

    header = Attribute(
        "An object that contains the header context information for this "
        "channel. Must provide IHeader")
    bytes = Attribute(
        "The total number of bytes that have been routed through this "
        "channel.")
    frames = Attribute(
        "The total number of frames that have been routed through this "
        "channel.")
    frameRemaining = Attribute(
        "The number of bytes that remain until another frame is completed.")

    def registerProducer(producer):
        """
        Registers a producer for this channel.
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

class IProducingChannel(IChannel):
    """
    A channel that produces data for RTMP encoding.
    """

class IConsumingChannel(IChannel):
    """
    A channel that consumes data from an RTMP bytestream.
    """

class IStream(Interface):
    """
    """

# Now the supporting classes

class IChannelManager(Interface):
    """
    Defines the interface for managing channels. The channel manager handles
    the interactions between its registered channels and the outside world ..
    """

    def getChannel(channelId):
        """
        Returns a L{IChannel} object based on the channeId.

        @raise IndexError: C{channelId} is not in range.
        @rtype: L{IChannel}
        """

    def createChannel():
        """
        Creates a channel using an unused channel id.
        """

    def registerChannel(channel, id):
        """
        Registers a C{channel} to the C{id}. 

        @param channel: An implementation of L{IChannel}.
        @type id: C{int}.
        @param producing: Whether this channel is producing.
        @type producing: C{bool}
        @raise IndexError: The C{id} is already in use or out of range.
        @raise OverflowError: There are no free channels.
        """

    def removeChannel(channel):
        """
        Removes a channel from this manager.

        @param channel: An implementation of L{IChannel}.
        @raise IndexError: The channel isn't registered to this manager.
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

    def frameReceived(channel, data):
        """
        A frame of data has been received from the channel. This is only
        called by non-producing channels.
        """
