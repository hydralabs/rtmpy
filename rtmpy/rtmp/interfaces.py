# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Interface documentation for RTMP primitives.

@since: 0.1
"""

from zope.interface import Interface, Attribute


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
        "U{RTMP datatypes on OSFlash<http://osflash.org/documentation/rtmp#rtmp_datatypes>} "
        "for a list of possibles.")
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
    observer = Attribute(
        "An L{IChannelObserver} object that listens for events on this "
        "channel.")

    def registerManager(manager):
        """
        Registers a channel manager.

        @param manager: L{IChannelManager}
        @raise TypeError: If manager does not provide L{IChannelManager}
        """

    def registerObserver(observer):
        """
        Registers an observer for this channel. If the channel is buffering
        data then the observer must be notified immediately.

        @param observer: L{IChannelObserver}
        @raise TypeError: If observer does not provide L{IChannelObserver}
        """

    def getHeader():
        """
        Returns the header for this channel. Returns C{None} if no header was
        applied to this channel.

        @rtype: L{IHeader} or C{None}.
        """

    def setHeader(header):
        """
        Sets the header for this channel. If the header is relative, then it
        is 'merged' with the last absolute header. If no header has been
        applied to this channel then L{IChannelManager.initialiseChannel} must
        be called.

        @param header: The header to apply to this channel.
        @type header: L{IHeader}
        @raise TypeError: If C{header} does not provide L{IHeader}
        """

    def dataReceived(data):
        """
        Called when data has been received for this channel. The channel must
        buffer the data until an observer has been registered.

        @type data: C{str}
        """

    def reset():
        """
        Called to reset the context information. Called when after a channel
        completes its body. This function should reset all contextual values
        except the header.
        """


class IChannelManager(Interface):
    """
    The channel manager handles the interactions between its registered
    channels and the outside world.
    """

    frameSize = Attribute(
        "A read-only C{int} that defines the size (in bytes) of each frame "
        "body. Set the frameSize via L{setFrameSize}")

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

    def channelComplete(channel):
        """
        Called when enough data has been written to the channel to satisfy
        the body. The manager's job is to act appropriately on the event.
        """

    def initialiseChannel(channel):
        """
        Called when a channel needs to be initialised to begin accepting data.
        This method must call L{IChannel.reset}.

        @param channel: The channel to initialise.
        @type channel: L{IChannel}
        """

    def setFrameSize(size):
        """
        Called to set the frame size, informing all registered channels of the
        update.

        @param size: The new frame size.
        @type size: C{int}
        """


class IChannelObserver(Interface):
    """
    Observes L{IChannel} events.
    """

    def dataReceived(data):
        """
        Called when the channel receives some data.

        @param data: The data received by the channel.
        @type data: C{str}
        """

    def bodyComplete():
        """
        Called when the amount of data received by the channel matches that
        of its header.
        """

    def headerChanged(header):
        """
        A new header was set on the channel.

        @param header: The new relative header.
        @type header: L{IHeader}
        """


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


class IHandshakeObserver(Interface):
    """
    Observes handshake events.
    """

    def handshakeSuccess():
        """
        Handshaking was successful.
        """

    def handshakeFailure(reason):
        """
        Handshaking failed.

        @param reason: Why the handshake failed.
        @type reason: Exception wrapped L{Failure}
        """

    def write(data):
        """
        Called when the handshake negotiator writes some data.
        """


class IHandshakeNegotiator(Interface):
    """
    Negotiates handshakes.
    """

    observer = Attribute(
        "An L{IHandshakeObserver} that listens for events from this "
        "negotiator")
    server = Attribute(
        "The server handshake token. Can be L{ServerToken} or C{None}")
    client = Attribute(
        "The client handshake token. Can be L{ServerToken} or C{None}")

    def start(uptime=None, version=None):
        """
        Called to start the handshaking process. You can supply the uptime and
        version, otherwise they will be worked out automatically. The version
        specifically will be set to enable H.264 streaming.
        """

    def dataReceived(self, data):
        """
        Called when handshaking data has been received.
        """


class IEvent(Interface):
    """
    An RTMP Event.

    @see: U{RTMP datatypes on OSFlash (external)
        <http://osflash.org/documentation/rtmp#rtmp_datatypes>}
    """

    def encode(bbs):
        """
        Encodes the event instance to C{bbs}. Can return a L{defer.Deferred}.

        @param bbs: A stream object to write to.
        @type bbs: L{rtmpy.util.BufferedByteStream}
        """

    def decode(bbs):
        """
        Decodes the event instance from C{bbs}. Can return a L{defer.Deferred}.

        @param bbs: A stream object to read from.
        @type bbs: L{rtmpy.util.BufferedByteStream}
        """

    def dispatch(listener):
        """
        Dispatch the event to the listener. Calls the correct method with the
        correct args according to L{IEventListener}.

        @param listener: Receives the event dispatch request.
        @type listener: L{IEventListener}
        @return: Whatever is returned by the call to C{listener}.
        @rtype: C{mixed}
        """


class IEventListener(Interface):
    """
    Receives dispatched events.
    """

    def onInvoke(invoke):
        """
        Called when an invoke event have been received.

        @param invoke: The object representing the call request. See
            L{rtmpy.rtmp.event.Invoke} for an example implementation.
        @return: The response, or a L{defer.Deferred} that will return the
            response.
        """

    def onNotify(notify):
        """
        Similar to L{onInvoke} but no response is expected and will be
        ignored.

        @param notify: The object representing the notify request.
        @return: Ignored
        """

    def onFrameSize(size):
        """
        Called when the RTMP frame size has changed.

        @param size: The new size of the frames.
        @type size: C{int}
        """

    def onBytesRead(bytes):
        """
        Called when the connected endpoint reports the number of raw bytes
        read from the stream.

        @param bytes: The number of bytes read.
        @type bytes: C{int}
        """

    def onControlMessage(message):
        """
        Called when a control message is received by the connected endpoint.

        @param message: The received message.
        @type message: L{rtmpy.rtmp.event.ControlMessage}
        """

    def onDownstreamBandwidth(bandwidth):
        """
        Called when the connected endpoint reports its downstream bandwidth
        limit.

        @param bandwidth: The amount of bandwidth available (it appears to be
            measured in KBps).
        @type bandwidth: C{int}
        """

    def onUpstreamBandwidth(bandwidth, extra):
        """
        Called when the connected endpoint reports its upstream bandwidth
        limit.

        @param bandwidth: The amount of bandwidth available (it appears to be
            measured in KBps).
        @type bandwidth: C{int}
        @param extra: Not quite sure what this represents atm.
        @type extra: C{int}
        """

    def onAudioData(data):
        """
        Called when audio data is received.

        @param data: The raw data received on the audio channel.
        @type data: C{str}
        """

    def onVideoData(data):
        """
        Called when video data is received.

        @param data: The raw data received on the video channel.
        @type data: C{str}
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


class IStreamable(Interface):
    """
    Flags the implementing class as streaming. Used for marking audio/video
    data events so that any observers are immediately notified.
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
