# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
RTMP codecs. Encoders and decoders for rtmp streams.

@see: U{RTMP<http://dev.rtmpy.org/wiki/RTMP>}
"""

import collections

from zope.interface import Interface, Attribute
from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import header, message

__all__ = [
    'Encoder',
    'Decoder'
]


#: The default number of bytes per RTMP frame (excluding header)
FRAME_SIZE = 128
#: Maximum number of channels that can be active per RTMP connection
MAX_CHANNELS = 0xffff + 64
MIN_CHANNEL_ID = 3

#: A list of encoded headers
_ENCODED_CONTINUATION_HEADERS = []


class BaseError(Exception):
    """
    Base error class for all things C{codec}.
    """


class DecodeError(BaseError):
    """
    Raised if there is an error decoding an RTMP byte stream.
    """


class EncodeError(BaseError):
    """
    Raised if there is an error encoding an RTMP byte stream.
    """


class IChannelMeta(Interface):
    """
    Contains meta data related to a channel.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    timestamp = Attribute("The relative time value for the associated message.")
    datatype = Attribute("The datatype for the corresponding channel.")
    bodyLength = Attribute("The length of the channel body.")
    streamId = Attribute("An C{int} representing the linked stream.")


class BaseChannel(object):
    """
    Marshals data in and out of RTMP frames.

    @ivar channelId: The id that this channel has been assigned (duh?!)
    @type channelId: C{int}
    @ivar header: The calculated header for this channel. RTMP can send
        relative headers, which will be merged with the previous headers to
        calculate the absolute values for the header.
    @type header: L{header.Header} or C{None}
    @ivar stream: The byte container which frames are marshalled.
    @type stream: L{BufferedByteStream}
    @ivar frameSize: The maximum number of bytes of an RTMP frame.
    @type frameSize: C{int}
    @ivar frameRemaining: The amount of data that needs to be received before
        a frame can be considered complete.
    @type frameRemaining: C{int}
    @ivar bytes: The total number of bytes that this channel has read/written
        since the last reset.
    """

    def __init__(self, channelId, stream, frameSize):
        self.channelId = channelId
        self.stream = stream
        self.frameSize = frameSize

        self.header = None

    def reset(self):
        self.bytes = 0
        self._bodyRemaining = -1
        self.frameRemaining = self.frameSize

    @property
    def complete(self):
        """
        Whether this channel has completed its content length requirements.
        """
        return self._bodyRemaining == 0

    def setHeader(self, new):
        """
        Applies a new header to this channel. If this channel has no previous
        header then the new header must be absolute (C{relative=False}).
        Otherwise the new values will be applied to the existing header.

        @param new: The header to apply to this channel.
        @type new: L{header.Header}
        @return: The previous header, if there is one.
        @rtype: L{header.Header} or C{None}
        """
        old_header = self.header

        if old_header is None:
            if new.relative is True:
                raise header.HeaderError(
                    'Tried to set a relative header as absolute')

        if not new.relative:
            h = self.header = new
        else:
            h = self.header = header.mergeHeaders(self.header, new)

        self._bodyRemaining = h.bodyLength - self.bytes

        return old_header

    def _adjustFrameRemaining(self, l):
        """
        Adjusts the C{frameRemaining} attribute based on the supplied length.
        """
        size = self.frameSize

        while l >= size:
            l -= size

        self.frameRemaining -= l

    def marshallFrame(self, size):
        """
        Marshalls an RTMP frame. Must be implemented by subclasses.

        @param size: The number of bytes to be marshalled.
        """
        raise NotImplementedError

    def marshallOneFrame(self):
        """
        Marshalls one RTMP frame and adjusts counters accordingly. Calls
        C{marshallFrame} which subclasses must implement.
        """
        l = min(self.frameRemaining, self.frameSize, self._bodyRemaining)

        ret = self.marshallFrame(l)

        self.bytes += l
        self._bodyRemaining -= l
        self._adjustFrameRemaining(l)

        return ret

    def __repr__(self):
        s = []
        attrs = ['channelId', 'frameRemaining', 'bytes']

        if self.header is None:
            s.append('header=None')
        else:
            s.append('channelId=%r' % (self.channelId,))
            s.append('datatype=%r' % (self.header.datatype,))

        for a in attrs:
            if not hasattr(self, a):
                continue

            s.append('%s=%r' % (a, getattr(self, a)))

        return '<%s.%s %s at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            ' '.join(s),
            id(self)
        )


class ConsumingChannel(BaseChannel):
    """
    Reads RTMP frames.
    """

    def marshallFrame(self, size):
        """
        Reads an RTMP frame from the stream and returns the content of the body.

        If there is not enough data to fulfill the frame requirements then
        C{IOError} will be raised.
        """
        return self.stream.read(size)


class ProducingChannel(BaseChannel):
    """
    Writes RTMP frames.

    @ivar buffer: Any data waiting to be written to the underlying stream.
    @type buffer: L{BufferedByteStream}
    """

    def __init__(self, channelId, stream, frameSize):
        BaseChannel.__init__(self, channelId, stream, frameSize)

        self.buffer = BufferedByteStream()

    def reset(self):
        """
        Called when the channel has completed writing the buffer.
        """
        BaseChannel.reset(self)

        self.buffer.seek(0)
        self.buffer.truncate()

    def append(self, data):
        """
        Appends
        """
        self.buffer.append(data)

    def marshallFrame(self, size):
        self.stream.write(self.buffer.read(size))


class Codec(object):
    """
    Generic channels and frame operations.

    @ivar stream: The underlying buffer containing the raw bytes.
    @type stream: L{BufferedByteStream}
    @ivar channels: A L{dict} of L{BaseChannel} objects that are handling data.
    @ivar frameSize: The maximum size for an individual frame. Read-only, use
        L{setFrameSize} instead.
    """

    def __init__(self, stream=None):
        self.stream = stream or BufferedByteStream()

        self.channels = {}
        self.frameSize = FRAME_SIZE

    def setFrameSize(self, size):
        """
        Set the size of the next frame to be handled.
        """
        self.frameSize = size

        for channel in self.channels.values():
            channel.frameSize = size

    def getChannel(self, channelId):
        """
        Returns a channel based on channelId. If the channel doesn't exist,
        then one is created.

        @param channelId: Index for the channel to retrieve.
        @type channelId: C{int}
        @rtype: L{Channel}
        """
        channel = self.channels.get(channelId, None)

        if channel is not None:
            return channel

        if channelId > MAX_CHANNELS:
            raise IndexError('Attempted to get channelId %d which is > %d' % (
                channelId, MAX_CHANNELS))

        channel = self.channel_class(channelId, self.stream, self.frameSize)
        self.channels[channelId] = channel

        channel.reset()

        return channel


class FrameReader(Codec):
    """
    A generator object that decodes RTMP frames from a data stream. Feed it data
    via L{send} and then iteratively call L{next}.

    A frame consists of a header and then a chunk of data. Each header will
    contain the channel that the frame is destined for. RTMP allows multiple
    channels to be interleaved together.
    """

    channel_class = ConsumingChannel

    def readHeader(self):
        """
        Reads an RTMP header from the stream.

        @rtype: L{header.Header}
        """
        return header.decodeHeader(self.stream)

    def send(self, data):
        """
        Adds more data to the stream for the reader to consume.
        """
        self.stream.append(data)

    def next(self):
        """
        Called to pull the next RTMP frame out of the stream. A tuple containing
        three items is returned::

         * the raw bytes for the frame
         * whether the channel is considered complete (i.e. all the data has been
            received)
         * An L{IChannelMeta} instance.

        If an attempt to read from the stream comes to a natural end then
        C{StopIteration} is raised, otherwise C{IOError}.
        """
        pos = self.stream.tell()

        try:
            h = self.readHeader()

            channel = self.getChannel(h.channelId)
            channel.setHeader(h)

            bytes = channel.marshallOneFrame()

            complete = channel.complete

            if complete:
                channel.reset()

            return bytes, complete, channel.header
        except IOError:
            self.stream.seek(pos, 0)

            if self.stream.at_eof():
                self.stream.consume()

                raise StopIteration

            raise

    def __iter__(self):
        return self


class ChannelDemuxer(FrameReader):
    """
    The next layer up from reading raw RTMP frames. Reassembles the interleaved
    channel data and dispatches the raw channel data when it is complete.

    There are two generic categories of channels in RTMP; streaming and
    non-streaming. Audio/Video data is considered streamable data, everything
    else is not. This means that the raw data is buffered until the channel is
    complete.

    @ivar bucket: Buffers any incomplete channel data.
    @type bucket: channel -> buffered data.
    """

    def __init__(self, stream=None):
        FrameReader.__init__(self, stream=stream)

        self.bucket = {}

    def next(self):
        """
        Read an RTMP frame and buffer the data (if necessary) until the channel
        is considered complete.

        Return a tuple containing:

        * the raw bytes for the channel
        * The associated L{IChannelMeta} instance

        C{None, None} will be returned if a frame was read, but no channel was
        complete.
        """
        data, complete, meta = FrameReader.next(self)

        if meta.datatype in message.STREAMABLE_TYPES:
            # don't buffer the data, pass it right on through
            return data, meta

        if complete:
            data = self.bucket.pop(meta.channelId, '') + data

            return data, meta

        channelId = meta.channelId

        self.bucket[channelId] = self.bucket.get(channelId, '') + data

        # nothing was available
        return None, None


class Decoder(ChannelDemuxer):
    """
    Dispatches decoded RTMP messages to a C{dispatcher}.

    At this layer, a message is a datatype, a timestamp and a blob of data. It
    is up to the dispatcher to decide how to handle the decoding of the data.

    @ivar dispatcher: Receives dispatched messages generated by the decoder.
    @ivar stream_factory: Builds stream listener objects.
    """

    channel_class = ConsumingChannel

    def __init__(self, dispatcher, stream_factory, stream=None):
        ChannelDemuxer.__init__(self, stream=stream)

        self.dispatcher = dispatcher
        self.stream_factory = stream_factory

    def next(self):
        """
        Iterates over the RTMP stream and dispatches decoded messages to the
        C{dispatcher}.

        This function does not return anything. Call it iteratively to pump RTMP
        messages out of the stream.

        If C{IOError} is raised, something went wrong decoding the stream,
        otherwise C{StopIteration} will be raised if the end of the stream is
        reached.
        """
        data, meta = ChannelDemuxer.next(self)

        if data is None:
            return

        stream = self.stream_factory.getStream(meta.streamId)

        stream.timestamp += meta.timestamp

        self.dispatcher.dispatchMessage(
            stream, meta.datatype, stream.timestamp, data)


class ChannelMuxer(Codec):
    """
    @ivar releasedChannels: A list of channel ids that have been released.
    @type releasedChannels: C{collections.deque}
    @ivar channelsInUse: Number of RTMP channels currently in use.
    @ivar activeChannels: A list of L{Channel} objects that are active (and
        therefore unavailable)
    """

    channel_class = ProducingChannel

    def __init__(self, stream=None):
        Codec.__init__(self, stream=stream)

        self.minChannelId = MIN_CHANNEL_ID
        self.releasedChannels = collections.deque()
        self.activeChannels = []
        self.channelsInUse = 0

        self.nextHeaders = {}
        self.timestamps = {}

    @apply
    def minChannelId():
        def fget(self):
            return self._minChannelId

        def fset(self, value):
            self._minChannelId = value
            self._maxChannels = MAX_CHANNELS - value

        return property(**locals())

    def aquireChannel(self):
        """
        Aquires and returns the next available L{Channel} or C{None}.

        In this context, aquire means to make the channel unavailable until the
        corresponding L{releaseChannel} call is made.

        There is no control over which channel you are going to be returned.

        @rtype: L{Channel} or C{None}
        """
        try:
            channelId = self.releasedChannels.popleft()
        except IndexError:
            channelId = self.channelsInUse + self._minChannelId

            if channelId >= MAX_CHANNELS:
                return None

        self.channelsInUse += 1

        c = self.getChannel(channelId)

        self.activeChannels.append(c)

        return c

    def releaseChannel(self, channelId):
        """
        Releases the channel such that a call to C{acquireChannel} will
        eventually return it.

        @param channelId: The id of the channel being released.
        """
        c = self.getChannel(channelId)

        try:
            # FIXME: this is expensive
            self.activeChannels.remove(c)
        except ValueError:
            raise EncodeError('Attempted to release channel %r but that '
                'channel is not active' % (channelId,))

        self.releasedChannels.appendleft(channelId)
        self.channelsInUse -= 1

    def isFull(self):
        """
        Need a better name for this
        """
        return self.channelsInUse == self._maxChannels

    def writeHeader(self, channel):
        """
        """
        h = self.nextHeaders.pop(channel, None)

        if h is None:
            if channel.channelId < 64:
                self.stream.write(
                    _ENCODED_CONTINUATION_HEADERS[channel.channelId])
            else:
                header.encodeHeader(self.stream, h)
        else:
            old_header = channel.setHeader(h)

            if old_header:
                h = header.diffHeaders(old_header, h)

            header.encodeHeader(self.stream, h)

    def send(self, data, datatype, streamId, timestamp):
        channel = self.aquireChannel()

        if not channel:
            raise EncodeError('Could not allocate channel')

        lastTimestamp = self.timestamps.get(streamId, 0)

        h = header.Header(channel.channelId, streamId=streamId,
            datatype=datatype, bodyLength=len(data),
            timestamp=timestamp - lastTimestamp)

        self.timestamps[streamId] = timestamp
        self.nextHeaders[channel] = h
        channel.append(data)

    def next(self):
        # 61 active channels might be too larger chunk of work for 1 iteration
        if not self.activeChannels:
            raise StopIteration

        to_release = []

        for channel in self.activeChannels:
            self.writeHeader(channel)
            channel.marshallOneFrame()

            if channel.complete:
                channel.reset()
                to_release.append(channel)

        [self.releaseChannel(channel.channelId) for channel in to_release]


class Encoder(ChannelMuxer):
    """
    @ivar pending: An fifo queue of messages that are waiting to be assigned a
        channel.
    """

    def __init__(self, output, stream=None):
        ChannelMuxer.__init__(self, stream=stream)

        self.pending = []
        self.output = output

    def send(self, data, datatype, streamId, timestamp):
        """
        """
        if self.isFull():
            self.pending.append((data, datatype, streamId, timestamp))

            return

        ChannelMuxer.send(self, data, datatype, streamId, timestamp)

    def next(self):
        while self.pending and not self.isFull():
            ChannelMuxer.send(self, *self.pending.pop(0))

        ChannelMuxer.next(self)

        self.output.write(self.stream.getvalue())
        self.stream.consume()


def build_header_continuations():
    global _ENCODED_CONTINUATION_HEADERS

    s = BufferedByteStream()

    # only generate the first 64 as it is likely that is all we will ever need
    for i in xrange(0, 64):
        h = header.Header(i)

        header.encodeHeader(s, h)

        _ENCODED_CONTINUATION_HEADERS.append(s.getvalue())
        s.consume()


build_header_continuations()
