# Copyright the RTMPy Project.
# See LICENSE for details.

"""
RTMP codecs. Encoders and decoders for rtmp streams.

@see: U{RTMP<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

from zope.interface import Interface, Attribute
from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import header, message


#: The default number of bytes per RTMP frame (excluding header)
FRAME_SIZE = 128

#: Maximum number of channels that can be active per RTMP stream
MAX_CHANNELS = 64


class BaseError(Exception):
    """
    Base error class for all things `codec`.
    """


class DecodeError(BaseError):
    """
    Raised if there is an error decoding an RTMP bytestream.
    """


class EncodeError(BaseError):
    """
    Raised if there is an error encoding an RTMP bytestream.
    """


class ProtocolError(BaseError):
    """
    Raised if an error occurs whilst handling the protocol.
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


class IMessageDelegate(Interface):
    """
    """

    def getStream(streamId):
        """
        """

    def dispatchMessage(stream, datatype, timestamp, data):
        """
        """


class Channel(object):
    """
    Acts as a container for an RTMP channel. Does not know anything of
    encoding or decoding channels, it is literally meant as a proxy between
    the byte stream and an observer.

    @ivar header: The calculated header for this channel. RTMP can send
        relative headers, which will be merged with the previous headers to
        calculate the absolute values for the header.
    @type header: L{interfaces.IHeader} or C{None}
    @ivar frameRemaining: The amount of data that needs to be received before
        a frame can be considered complete.
    @type frameRemaining: C{int}
    """

    def __init__(self, codec, stream):
        self.header = None
        self.codec = codec
        self.stream = stream
        self.frameSize = self.codec.frameSize

        self.reset()

    def reset(self):
        self.bytes = 0
        self.bodyRemaining = None
        self.frameRemaining = self.frameSize

    def setHeader(self, new):
        """
        Applies a new header to this channel. If this channel has no previous
        header then the new header must be absolute (C{relative=True}).
        Otherwise the new values will be applied to the existing header.
        Setting the header requires a registered manager.

        @param header: The header to apply to this channel.
        @type header: L{interfaces.IHeader}
        """
        old_header = self.header

        if old_header is None:
            if new.relative is True:
                raise header.HeaderError(
                    'Tried to set a relative header as absolute')
        else:
            if new.channelId != self.header.channelId:
                raise header.HeaderError('Tried to assign a header from a '
                    'different channel (original:%r, new:%r)' % (
                        self.header.channelId, new.channelId))

        if new.relative:
            self.header = header.mergeHeaders(self.header, new)
        else:
            self.header = new

        self.bodyRemaining = self.header.bodyLength - self.bytes

    def _adjustFrameRemaining(self, l):
        """
        Adjusts the C{frameRemaining} attributes based on the supplied length.
        """
        size = self.frameSize

        while l >= size:
            l -= size

        if l >= self.frameRemaining:
            l -= self.frameRemaining
            self.frameRemaining = size

        self.frameRemaining -= l

    def readFrame(self):
        """
        Reads an RTMP frame from the stream and returns the content of the body.

        If ther is not enough data to fulfill the frame requirements then
        C{IOError} will be raised.
        """
        l = min(self.frameRemaining, self.frameSize, self.bodyRemaining)

        bytes = self.stream.read(l)

        self.bytes += l
        self.bodyRemaining -= l
        self._adjustFrameRemaining(l)

        return bytes

    def __repr__(self):
        s = []
        attrs = ['frameRemaining', 'frames', 'bytes', 'bodyRemaining']

        if self.header is None:
            s.append('header=None')
        else:
            s.append('channelId=%r' % (self.header.channelId,))
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


class Codec(object):
    """
    Generic channels and frame operations.

    @ivar stream: The underlying buffer containing the raw bytes.
    @type stream: L{BufferedByteStream}
    @ivar channels: A L{dict} of L{Channel} objects that are awaiting data.
    @ivar frameSize: The maximum size for an individual frame. Read-only, use
        L{setFrameSize} instead.
    """

    def __init__(self, stream=None):
        self.stream = stream or BufferedByteStream()

        self.channels = {}
        self.frameSize = FRAME_SIZE

    def setFrameSize(self, size):
        """
        Set the size of the next frame to be read.
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

        channel = self.channels[channelId] = Channel(self, self.stream)

        return channel


class FrameReader(Codec):
    """
    A generator object that decodes RTMP frames from a data stream. Feed it data
    via L{send} and then iteratively call L{next}.

    A frame consists of a header and then a chunk of data. Each header will
    contain the channel that the frame is destined for. RTMP allows multiple
    channels to be interleaved together.
    """

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
        three items is returned:

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

            bytes = channel.readFrame()

            complete = channel.bodyRemaining == 0

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

    def __init__(self, dispatcher, stream_factory, stream=None):
        ChannelDemuxer.__init__(self, stream=stream)

        self.dispatcher = dispatcher
        self.stream_factory = stream_factory

    def next(self):
        """
        Iterates over the RTMP stream and dispatches messages to the
        C{dispatcher}.

        This function does not return anything. Call it iteratively to pump RTMP
        messages out of the stream. If C{IOError} is raised, something went
        wrong decoding the stream, otherwise C{StopIteration} will be raised if
        the end of the stream is reached.
        """
        data, meta = ChannelDemuxer.next(self)

        if data is None:
            return

        stream = self.stream_factory.getStream(meta.streamId)

        stream.timestamp += meta.timestamp

        self.dispatcher.dispatchMessage(
            stream, meta.datatype, stream.timestamp, data)


class Encoder(object):
    """
    """

    def __init__(self, stream=None):
        self.messages = []

    def send(streamId, datatype, timestamp, data):
        self.messages.append((streamId, datatype, timestamp, data))

    def next(self):
        for message in messages:
            pass