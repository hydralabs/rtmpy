from zope.interface import Interface, Attribute, implements



class IChannelMeta(Interface):
    """
    Contains meta data related to a channel.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    timestamp = Attribute("The relative time value for the associated message.")
    datatype = Attribute("The datatype for the corresponding channel.")
    bodyLength = Attribute("The length of the channel body.")
    streamId = Attribute("An C{int} representing the linked stream.")



class IMessageDispatcher(Interface):
    """
    """

    def dispatchMessage(stream, datatype, timestamp, data):
        """
        Called when an RTMP message has been completely received.

        @param stream: The L{Stream} to receive this mesage.
        @param datatype: The RTMP datatype for the message.
        @param timestamp: The absolute timestamp this message was received.
        @param data: The raw data for the message.
        """


    def bytesInterval(bytes):
        """
        Called when a specified number of bytes has been read from the stream.
        The RTMP protocol demands that we send an acknowledge message to the
        peer. If we don't do this, Flash will stop streaming video/audio.

        @param bytes: The number of bytes read when this interval was fired.
        """



class IStreamManager(Interface):
    """
    """
