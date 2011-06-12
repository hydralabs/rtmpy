# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
RTMP codecs. Encoders and decoders for RTMP streams.

This module purposefully does not have third party dependencies (save for PyAMF,
which does all the byte packing).

The Encoder/Decoder is not thread safe.

@see: U{RTMP<http://dev.rtmpy.org/wiki/RTMP>}
@todo: Provide a way to introspect the 'state' of the codec to allow admin type
   facilities. To be worked out in the future.
"""

import collections

from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import header
from rtmpy import message



__all__ = [
    'Encoder',
    'Decoder',
    'DecodeError',
    'EncodeError',
    'StreamingChannel'
]



#: The default number of bytes per RTMP frame (excluding header)
FRAME_SIZE = 128
#: Maximum number of channels that can be active per RTMP connection
MAX_CHANNELS = 0xffff + 64 - 2
#: An RTMP channel with an id of 0 is special as it is considered the control
#  stream. It cannot be deleted and is integral to the RTMP protocol.
COMMAND_CHANNEL_ID = 0



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
    @type bytes: C{int}
    """


    def __init__(self, channelId, stream, frameSize):
        self.channelId = channelId
        self.stream = stream
        self.frameSize = frameSize
        self.bytes = 0
        self.timestamp = 0
        self._lastDelta = 0

        self.header = None


    def reset(self):
        self.bytes = 0
        self._bodyRemaining = -1
        self.frameRemaining = self.frameSize


    def complete(self):
        """
        Whether this channel has completed its content length requirements.
        """
        return self._bodyRemaining == 0


    def setHeader(self, new):
        """
        Applies a new header to this channel. If this channel already has a
        header, then the new values are merged with the existing.

        @param new: The header to apply to this channel.
        @type new: L{header.Header}
        @return: The previous header, if there is one.
        @rtype: L{header.Header} or C{None}
        """
        old = self.header

        if self.header is None:
            self.header = new
        else:
            self.header = header.merge(self.header, new)

        if new.timestamp == -1:
            # receiving a new message and no timestamp has been supplied means
            # we use the last known
            if self.bytes == 0:
                self.setTimestamp(self._lastDelta, True)
        else:
            if not new.continuation:
                self.setTimestamp(new.timestamp, not new.full)

        self._bodyRemaining = self.header.bodyLength - self.bytes

        return old


    def marshallFrame(self, size):
        """
        Marshalls an RTMP frame from the C{stream}.

        Must be implemented by subclasses.

        @param size: The number of bytes to be marshalled.
        """
        raise NotImplementedError


    def marshallOneFrame(self):
        """
        Marshalls one RTMP frame and adjusts internal counters accordingly.
        Calls C{marshallFrame} which subclasses must implement.
        """
        frameSize = self.frameSize
        l = min(self.frameRemaining, frameSize, self._bodyRemaining)

        ret = self.marshallFrame(l)

        self.bytes += l
        self._bodyRemaining -= l

        while l >= frameSize:
            l -= frameSize

        self.frameRemaining -= l

        return ret


    def setFrameSize(self, size):
        """
        Sets the size of the RTMP frame for this channel.

        @param size: The new size of the RTMP frame.
        @type size: C{int}
        """
        if self.frameRemaining >= self.frameSize:
            self.frameRemaining = size

        self.frameSize = size


    def setTimestamp(self, timestamp, relative=True):
        """
        Sets the timestamp for this stream. The timestamp is measured in
        milliseconds since an arbitrary epoch. This could be since the stream
        started sending or receiving audio/video etc.

        @param relative: Whether the supplied timestamp is relative to the
            previous.
        """
        if relative:
            self._lastDelta = timestamp
            self.timestamp += timestamp
        else:
            if self.timestamp == 0:
                self._lastDelta = timestamp

            self.timestamp = timestamp


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
    @ivar acquired: Whether this channel is acquired. See L{ChannelMuxer.
        acquireChannel}
    """


    def __init__(self, channelId, stream, frameSize):
        BaseChannel.__init__(self, channelId, stream, frameSize)

        self.buffer = BufferedByteStream()
        self.acquired = False
        self.callback = None


    def setCallback(self, cb):
        """
        Sets the callback that will be fired once this channel has been completely
        encoded.
        """
        self.callback = cb


    def reset(self):
        """
        Called when the channel has completed writing the buffer.
        """
        BaseChannel.reset(self)

        self.buffer.seek(0)
        self.buffer.truncate()
        self.header = None


    def append(self, data):
        """
        Appends data to the buffer in preparation of encoding in RTMP.
        """
        self.buffer.append(data)


    def marshallFrame(self, size):
        """
        Writes a section of the buffer as part of the RTMP frame.
        """
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
        self.bytes = 0


    def setFrameSize(self, size):
        """
        Set the size of the next frame to be handled.
        """
        self.frameSize = size

        for channel in self.channels.values():
            channel.setFrameSize(size)


    def buildChannel(self, channelId):
        """
        Called to build a channel suitable for use with this codec.

        Must be implemented by subclasses.
        """
        raise NotImplementedError


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

        channel = self.buildChannel(channelId)
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


    _currentChannel = None


    def buildChannel(self, channelId):
        """
        Builds a channel object that is capable of marshalling frames from the
        stream.
        """
        return ConsumingChannel(channelId, self.stream, self.frameSize)


    def readHeader(self):
        """
        Reads an RTMP header from the stream.

        @rtype: L{header.Header}
        """
        return header.decode(self.stream)


    def send(self, data):
        """
        Adds more data to the stream for the reader to consume.
        """
        self.stream.append(data)


    def readFrame(self):
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
        channel = self._currentChannel

        if channel is None:
            try:
                h = self.readHeader()
            except IOError:
                self.stream.seek(pos, 0)

                raise

            new_pos = self.stream.tell()
            self.bytes += new_pos - pos
            pos = new_pos

            channel = self._currentChannel = self.getChannel(h.channelId)

            channel.setHeader(h)

        try:
            bytes = channel.marshallOneFrame()
        except IOError:
            self.stream.seek(pos, 0)

            raise
        else:
            self._currentChannel = None

        self.bytes += self.stream.tell() - pos
        complete = channel.complete()
        h = channel.header

        if complete:
            h.timestamp = channel.timestamp

            channel.reset()

        return bytes, complete, h


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


    def readFrame(self):
        """
        Read an RTMP frame and buffer the data (if necessary) until the channel
        is considered complete.

        Return a tuple containing:

        * the raw bytes for the channel
        * The associated L{IChannelMeta} instance

        C{None, None} will be returned if a frame was read, but no channel was
        complete.
        """
        data, complete, meta = FrameReader.readFrame(self)

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
    @type dispatcher: Provides L{interfaces.IMessageDispatcher}
    @ivar stream_factory: Builds stream listener objects.
    @type stream_factory: L{interfaces.IStreamManager}
    """


    channel_class = ConsumingChannel


    def __init__(self, dispatcher, stream_factory, stream=None,
                 bytesInterval=0):
        ChannelDemuxer.__init__(self, stream=stream)

        self.dispatcher = dispatcher
        self.stream_factory = stream_factory

        self.setBytesInterval(bytesInterval)


    def setBytesInterval(self, bytesInterval):
        """
        Sets the interval at which the decoder must inform the dispatcher that
        a threshold of decoded bytes has been reached.
        """
        self.bytesInterval = bytesInterval
        self._nextInterval = self.bytes + self.bytesInterval


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
        try:
            data, meta = ChannelDemuxer.readFrame(self)
        except IOError:
            self.stream.consume()

            raise StopIteration

        if self.bytesInterval and self.bytes >= self._nextInterval:
            self.dispatcher.bytesInterval(self.bytes)
            self._nextInterval += self.bytesInterval

        if data is None:
            return

        stream = self.stream_factory.getStream(meta.streamId)

        self.dispatcher.dispatchMessage(
            stream, meta.datatype, meta.timestamp, data)


    __next__ = next


class ChannelMuxer(Codec):
    """
    Manages RTMP channels and marshalls the data so that the channels can be
    interleaved.

    @ivar releasedChannels: A list of channel ids that have been released.
    @type releasedChannels: C{collections.deque}
    @ivar channelsInUse: Number of RTMP channels currently in use.
    @ivar activeChannels: A list of L{BaseChannel} objects that are active (and
        therefore unavailable)
    @ivar nextHeaders: A collection of L{header.Header}s to be applied to the
        channel the next time it is asked to marshall a frame.
    @ivar timestamps: A collection of last known timestamps for a given channel.
        If the timestamp differs then the relative value is written assuming
        that the streamId hasn't changed.
    @ivar callbacks: A collection of channel->callback (if any).
    """


    def __init__(self, stream=None):
        Codec.__init__(self, stream=stream)

        self.pending = []

        self.releasedChannels = collections.deque()
        self.activeChannels = {}
        self.channelsInUse = 0

        self.nextHeaders = {}
        self.timestamps = {}


    def buildChannel(self, channelId):
        """
        Returns a channel that is capable of receiving data and marshalling RTMP
        frames to the stream.
        """
        return ProducingChannel(channelId, self.stream, self.frameSize)


    def acquireChannel(self):
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
            channelId = self.channelsInUse + 1

            if channelId > MAX_CHANNELS:
                return None

        self.channelsInUse += 1

        c = self.getChannel(channelId)
        c.acquired = True

        return c


    def releaseChannel(self, channelId):
        """
        Releases the channel such that a call to C{acquireChannel} will
        eventually return it.

        @param channelId: The id of the channel being released.
        """
        c = self.getChannel(channelId)

        if c.acquired is False:
            raise EncodeError('Attempted to release an inactive channel '
                '(channelId=%r)' % (channelId,))

        c.acquired = False
        self.releasedChannels.appendleft(channelId)
        self.channelsInUse -= 1


    def writeHeader(self, channel):
        """
        Encodes the next header for C{channel}.
        """
        h = self.nextHeaders.pop(channel, None)

        if h is not None:
            h = channel.setHeader(h)
        else:
            h = channel.header

        header.encode(self.stream, channel.header, h)


    def flush(self):
        """
        Flushes the internal buffer.
        """
        raise NotImplemented


    def _encodeOneFrame(self, channel):
        self.writeHeader(channel)
        channel.marshallOneFrame()

        c = channel.complete()

        if c is True and channel.callback is not None:
            try:
                channel.callback()
            except:
                pass

        return c


    def send(self, data, datatype, streamId, timestamp, whenDone=None):
        """
        Queues an RTMP message to be encoded. Call C{next} to do the encoding.

        @param data: The raw data that will be marshalled into RTMP frames and
            sent to the peer.
        @type data: C{str}
        @param datatype: The type of data. See C{message} for a list of known
            RTMP types.
        @type datatype: C{int}
        @param streamId: The C{NetStream} id that this message is intended for.
        @type streamId: C{int}
        @param timestamp: The current timestamp for the stream that this message
            was sent.
        @type timestamp: C{int}
        """
        if is_command_type(datatype):
            # we have to special case command types because a channel only be
            # busy with one message at a time. Command messages are always
            # written right away
            channel = self.getChannel(COMMAND_CHANNEL_ID)
        else:
            channel = self.acquireChannel()

            if not channel:
                self.pending.append((data, datatype, streamId, timestamp, whenDone))

                return

        h = header.Header(
            channel.channelId,
            timestamp - channel.timestamp,
            datatype,
            len(data),
            streamId)

        if whenDone is not None:
            channel.setCallback(whenDone)

        channel.append(data)
        self.nextHeaders[channel] = h

        if channel.channelId == COMMAND_CHANNEL_ID:
            while not self._encodeOneFrame(channel):
                pass

            channel.reset()
            self.flush()

            return

        self.activeChannels[channel] = channel.channelId


    def next(self):
        """
        Encodes one RTMP frame from all the active channels.
        """
        while self.pending and self.channelsInUse <= MAX_CHANNELS:
            self.send(*self.pending.pop(0))

        if not bool(self.activeChannels):
            raise StopIteration

        to_release = []

        for channel in self.activeChannels:
            if self._encodeOneFrame(channel):
                channel.reset()
                to_release.append(channel)

        for channel in to_release:
            self.releaseChannel(channel.channelId)
            del self.activeChannels[channel]



class Encoder(ChannelMuxer):
    """
    Encodes RTMP streams.

    Send RTMP encoded messages via L{send} and then call L{next} iteratively to
    get an RTMP stream.

    To think about::
        - Stale messages; A timestamp less than the last known timestamp.

    @ivar pending: An fifo queue of messages that are waiting to be assigned a
        channel.
    @ivar output: A C{write}able object that will receive the final encoded RTMP
        stream. The instance only needs to implement C{write} and accept 1 param
        (the data).
    """


    def __init__(self, output, stream=None):
        ChannelMuxer.__init__(self, stream=stream)

        self.output = output


    def next(self):
        """
        Called iteratively to produce an RTMP encoded stream.
        """
        ChannelMuxer.next(self)

        self.flush()


    def flush(self):
        """
        Flushes the internal buffer to C{output}.
        """
        s = self.stream.getvalue()

        self.output.write(s)
        self.stream.consume()

        self.bytes += len(s)

    @property
    def active(self):
        return bool(self.activeChannels)

    def __iter__(self):
        return self


    __next__ = next



class StreamingChannel(object):
    """
    """


    def __init__(self, channel, streamId, output):
        self.type = None
        self.channel = channel
        self.streamId = streamId
        self.output = output
        self.stream = BufferedByteStream()

        self._lastHeader = None
        self._oldStream = channel.stream
        channel.stream = self.stream

        h = header.Header(channel.channelId)

        # encode a continuation header for speed
        header.encode(self.stream, h, h)

        self._continuationHeader = self.stream.getvalue()
        self.stream.consume()


    def __del__(self):
        try:
            self.channel.stream = self._oldStream
        except:
            pass


    def setType(self, type):
        self.type = type


    def sendData(self, data, timestamp):
        c = self.channel

        if timestamp < c.timestamp:
            relTimestamp = timestamp
        else:
            relTimestamp = timestamp - c.timestamp

        h = header.Header(c.channelId, relTimestamp, self.type, len(data), self.streamId)

        if self._lastHeader is None:
            h.full = True

        c.setHeader(h)
        c.append(data)

        header.encode(self.stream, h, self._lastHeader)
        self._lastHeader = h

        c.marshallOneFrame()

        while not c.complete():
            self.stream.write(self._continuationHeader)
            c.marshallOneFrame()

        c.reset()
        self.output.write(self.stream.getvalue())
        self.stream.consume()



def is_command_type(datatype):
    """
    Determines if the data type supplied is a command type. This means that the
    related RTMP message must be marshalled on channel id = 2.
    """
    return datatype <= message.UPSTREAM_BANDWIDTH
