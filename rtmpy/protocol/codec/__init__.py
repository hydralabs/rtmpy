# Copyright the RTMPy Project.
# See LICENSE for details.

"""
RTMP codecs. Encoders and decoders for rtmp streams.

@see: U{RTMP<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

from twisted.internet import reactor, task, defer
from zope.interface import implements, Interface, Attribute
from pyamf.util import BufferedByteStream

from rtmpy import protocol
from rtmpy.protocol import interfaces, event
from rtmpy.protocol.codec import header as _header


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


class ChannelError(BaseError):
    """
    Raised when a channel operation goes wrong.
    """


class IChannelMeta(Interface):
    """
    Contains meta data related to a channel.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    timestamp = Attribute(
        "An C{int} time value - not sure what this represents atm.")
    datatype = Attribute("The datatype for the corresponding channel.")
    bodyLength = Attribute(
        "An C{int} which represents the length of the channel body.")
    streamId = Attribute(
        "An C{int} representing the linked stream.")


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

    implements(interfaces.IChannel)

    header = None

    def __init__(self, codec, stream):
        self.codec = codec
        self.stream = stream
        self.frameSize = self.codec.frameSize

        self.reset()

    def reset(self):
        self.bytes = 0
        self.bodyRemaining = None
        self.frameRemaining = self.frameSize

    def getHeader(self):
        """
        Gets the header for this channel. The header contains the absolute
        values for all received headers in the stream.

        @rtype: L{interfaces.IHeader} or C{None}
        """
        return self.header

    def setHeader(self, header):
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
            if header.relative is True:
                raise _header.HeaderError(
                    'Tried to set a relative header as absolute')
        else:
            if header.channelId != self.header.channelId:
                raise _header.HeaderError('Tried to assign a header from a '
                    'different channel (original:%r, new:%r)' % (
                        self.header.channelId, header.channelId))

        if header.relative:
            self.header = _header.mergeHeaders(self.header, header)
        else:
            self.reset()

            self.header = header

        self.bodyRemaining = self.header.bodyLength - self.bytes

    @property
    def channelId(self):
        return self.header.channelId

    @property
    def datatype(self):
        return self.header.datatype

    @property
    def streamId(self):
        return self.header.streamId

    def _adjustFrameRemaining(self, l):
        """
        Adjusts the C{frames} and C{frameRemaining} attributes based on the
        supplied length C{l}.
        """
        size = self.frameSize

        while l >= size:
            l -= size

        if l >= self.frameRemaining:
            l -= self.frameRemaining
            self.frameRemaining = size

        self.frameRemaining -= l

    def readFrame(self):
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


class BaseCodec(object):
    """
    Abstract functionality for an rtmp codec. Manages the creation/deletion
    and general maintenance of the channels linked to a connected RTMP
    stream. Also handles any events that channels may fire.

    @ivar deferred: The deferred from the result of L{getJob}.
    @type deferred: L{Deferred<twisted.internet.defer.Deferred>}
    @ivar job: A L{task.LoopingCall<twisted.internet.task.LoopingCall>}
        instance that is used to iteratively call the method supplied by
        L{getJob}.
    @ivar channels: A collection of channels.
    @type channels: C{dict} of C{id: L{Channel}}
    @ivar frameSize: The number of bytes for each frame content.
    @type frameSize: C{int}
    @ivar bytes: The number of raw bytes that has been en/decoded.
    @type bytes: C{int}
    @ivar bytesInterval: The number of bytes that must be en/decoded before
        L{ICodecObserver.onBytesInterval} will be called.
    """

    implements(interfaces.ICodec, interfaces.IChannelManager)

    channel_class = Channel

    #: The value at which the bytes read must be reset
    bytesReadReset = 0xee800000

    def __init__(self, protocol):
        self.protocol = protocol
        self.channels = {}
        self.activeChannels = []
        self.observer = None
        self.bytes = self.totalBytes = 0

        self.deferred = None
        self.frameSize = FRAME_SIZE

        self.buffer = BufferedByteStream()
        self.job = task.LoopingCall(self.getJob())

        self.debug = rtmp.DEBUG

    def __del__(self):
        if hasattr(self, 'job') and self.job.running:
            self.job.stop()

    def registerObserver(self, observer):
        """
        Registers an observer to listen to this codec.

        @type observer: L{interfaces.ICodecObserver}
        """
        self.observer = observer

    def getJob(self):
        """
        Returns the method to be iteratively called to process the codec.

        This method is intended to be implemented by sub-classes.
        """
        raise NotImplementedError()

    def start(self):
        """
        Starts or resumes the job. If the job is already running (i.e. not
        stopped) then this is a noop.
        """
        if self.job.running:
            return

        self.deferred = self.job.start(0, now=False)

        if self.observer is not None:
            self.observer.started()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Started job')

    def pause(self):
        """
        Pauses the codec. Called when the buffer is exhausted. If the job is
        already stopped then this is a noop.
        """
        if not self.job.running:
            return

        self.job.stop()

        if self.observer is not None:
            self.observer.stopped()

        self.deferred = None

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Stopped job')

    # interfaces.IChannelManager

    def createChannel(self, channelId):
        """
        A factory method that builds C{Channel} objects and registers them to
        this manager.

        @param channelId: The id of the channel
        @return: The newly instantiated channel.
        @rtype: L{Channel}
        """
        if channelId in self.channels:
            raise IndexError(
                'A channel is already registered to id %r' % (channelId,))

        if channelId < 0 or channelId > MAX_CHANNELS:
            raise IndexError("channelId is out of range (got:%d)" % (
                channelId,))

        channel = self.channels[channelId] = self.channel_class(self)
        self.channels[channel] = channelId

        return channel

    def getChannel(self, channelId):
        """
        Returns a channel based on channelId. If the channel doesn't exist,
        then one is created.

        @param channelId: Index for the channel to retrieve.
        @type channelId: C{int}
        @rtype: L{Channel}
        """
        try:
            return self.channels[channelId]
        except KeyError:
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Creating channel %d' % (channelId,))

            return self.createChannel(channelId)

    def getNextAvailableChannelId(self):
        """
        Returns a free channelId.
        """
        keys = self.activeChannels
        keys.sort()

        if len(keys) == MAX_CHANNELS:
            raise OverflowError("No free channel")

        for count in xrange(0, MAX_CHANNELS):
            try:
                if keys[count] != count:
                    return count
            except IndexError:
                return count

            count += 1

    def deactivateChannel(self, channel):
        """
        Flags a channel as inactive. If the channel is already inactive then
        this is a noop. If the codec has no other active channels it will
        L{pause} itself.

        @param channel: The channel registered to this codec.
        @type channel: L{IChannel}
        """
        try:
            channelId = self.channels[channel]
        except KeyError:
            raise RuntimeError('Channel is not registered to this codec')

        try:
            self.activeChannels.remove(channelId)
        except ValueError:
            pass

        if len(self.activeChannels) == 0 and self.shouldPause():
            self.pause()

    def shouldPause(self):
        return True

    def activateChannel(self, channel):
        """
        Flags a channel as active. If the channel is already active then this
        is a noop. If the codec has no other active channels it will L{start}
        itself.

        @param channel: The channel registered to this codec.
        @type channel: L{IChannel}
        """
        try:
            channelId = self.channels[channel]
        except KeyError:
            raise RuntimeError('Channel is not registered to this codec')

        if channelId in self.activeChannels:
            return

        self.activeChannels.append(channelId)

        if self.deferred is None:
            self.start()

    def channelComplete(self, channel):
        """
        Called when the body of the channel has been satisfied.
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'channelComplete(%s)' % (channel,))

        header = channel.getHeader()

        channel.reset()

    def initialiseChannel(self, channel, oldHeader):
        """
        Called when a header has been applied to an inactive channel.

        @param channel: The channel that the new header has been applied to.
        @type channel: L{Channel}
        @param oldHeader: The previous header on the channel before the new
            one was applied.
        @type oldHeader: L{Header}
        """
        if channel.manager != self:
            raise ValueError("Cannot initialise a channel that isn\'t "
                "registered to this manager")

        channel.reset()
        header = channel.getHeader()

    def setFrameSize(self, size):
        self.frameSize = size

        for channelId, channel in self.channels.iteritems():
            if isinstance(channel, Channel):
                channel.frameRemaining = size


class Decoder(BaseCodec):
    """
    Decodes an RTMP stream. De-interlaces the channels and writes the frames
    to the individual buffers. The decoder has the power to pause itself, but
    not to start.

    @ivar currentChannel: The channel currently being decoded.
    @type currentChannel: L{interfaces.IChannel}
    """

    def __init__(self, protocol):
        BaseCodec.__init__(self, protocol)

        self.currentChannel = None
        self.nextBytesRead = self.protocol.bytesReadInterval

    def getJob(self):
        return self.decode

    def pause(self):
        """
        Pauses the codec. Called when the buffer is exhausted. If the job is
        already stopped then this is a noop.
        """
        if not self.job.running:
            return

        self.job.stop()

        if self.observer is not None:
            self.observer.stopped()

        self.deferred = None
        # delete the bytes that have already been decoded
        self.buffer.consume()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Stopped job')

    def shouldPause(self):
        return len(self.buffer) == 0

    def readHeader(self):
        """
        Reads an RTMP Header from the stream. If there is not enough data in
        the buffer then C{None} is returned.

        @rtype: L{interfaces.IHeader} or C{None}
        """
        headerPosition = self.buffer.tell()

        try:
            return _header.decodeHeader(self.buffer)
        except IOError:
            self.buffer.seek(headerPosition)

            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Not enough data to read header. '
                    'Rewinding to %d' % (headerPosition,))

            return None

    def getBytesAvailableForChannel(self, channel):
        """
        Returns the number of bytes available in the buffer to be read as an
        RTMP stream.

        @type channel: L{interfaces.IChannel}
        """
        return min(
            channel.frameRemaining,
            channel.bodyRemaining,
            self.buffer.remaining(),
            self.frameSize
        )

    def readFrame(self):
        """
        This function attempts to read a frame from the stream. A frame is a
        set amount of data that borders header bytes. If a full frame was read
        from the buffer then L{currentChannel} is set to C{None}.

        After this function is finished, the next part of the buffer will
        either be empty or a header section.
        """
        if self.currentChannel is None:
            raise DecodeError('Channel is required to read frame')

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Reading frame for %r' % (self.currentChannel,))

        available = self.getBytesAvailableForChannel(self.currentChannel)

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, '%d bytes available' % (available,))

        if available < 0:
            raise DecodeError('%d bytes available for %r' % (
                available, self.currentChannel,))

        if available == 0:
            return

        frames = self.currentChannel.frames

        self.currentChannel.dataReceived(self.buffer.read(available))

        if self.currentChannel and self.currentChannel.frames != frames:
            # a complete frame was read from the stream which means a new
            # header and frame body will be next in the stream
            self.currentChannel = None

    def canContinue(self, minBytes=1):
        """
        Checks to see if decoding can continue. If there are less bytes in the
        stream than C{minBytes} then the job is paused.

        @param minBytes: The minimum number of bytes required to continue
            decoding.
        @type minBytes: C{int}
        @rtype: C{bool}
        """
        remaining = self.buffer.remaining()

        if remaining < minBytes or remaining == 0:
            self.pause()

        return (remaining >= minBytes)

    def _decode(self):
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'currentChannel = %r' % (self.currentChannel,))

        if self.currentChannel is not None:
            self.readFrame()

        if not self.canContinue():
            # the buffer is empty
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'buffer exhausted')

            self.pause()

            return

        pos = self.buffer.tell()
        h = self.readHeader()

        if h is None:
            # not enough bytes left in the stream to continue decoding, we
            # require a complete header to decode
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Not enough buffer to read header '
                    '(%d:remaining)' % (self.buffer.remaining(),))

            self.pause()

            return

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Read header %r' % (h,))

        self.currentChannel = self.getChannel(h.channelId)

        if self.debug or rtmp.DEBUG:
            if h.relative is True:
                rtmp.log(self, 'before %r' % self.currentChannel.getHeader())

        self.currentChannel.setHeader(h)

        if self.debug or rtmp.DEBUG:
            if h.relative is True:
                rtmp.log(self, 'after %r' % self.currentChannel.getHeader())

        self.readFrame()

    def checkBytesRead(self):
        if self.bytes > BaseCodec.bytesReadReset:
            self.bytes = 0
            self.nextBytesRead = self.protocol.bytesReadInterval

            return
        elif self.bytes < self.nextBytesRead:
            return

        self.nextBytesRead += self.protocol.bytesReadInterval

        self.protocol.bytesRead(self.bytes)

    def decode(self):
        """
        Attempt to decode the buffer. If a successful frame was decoded from
        the stream then the decoded bytes are removed.
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Decode (tell:%d, length:%d)' % (
                self.buffer.tell(), len(self.buffer),))

        if not self.canContinue():
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Buffer exhausted')

            self.pause()

            return

        self._decode()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Complete decode (buffer: length:%d)' % (
                len(self.buffer)))

    def dataReceived(self, data):
        """
        Adds data to the end of the stream.
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Received %d bytes' % (len(data),))

        t = self.buffer.tell()

        self.buffer.seek(0, 2)
        self.buffer.write(data)
        self.buffer.seek(t)

        self.start()

        l = len(data)
        self.bytes += l
        self.totalBytes += l

        self.checkBytesRead()

    def channelComplete(self, channel):
        """
        Called when the body of the channel has been satisfied.
        """
        BaseCodec.channelComplete(self, channel)

        self.deactivateChannel(channel)

        self.currentChannel = None

        header = channel.getHeader()
        stream = self.protocol.getStream(header.streamId)

        stream.channelUnregistered(channel)

    def initialiseChannel(self, channel, oldHeader):
        """
        Called when a header has been applied to an inactive channel.
        """
        BaseCodec.initialiseChannel(self, channel, oldHeader)

        header = channel.getHeader()

        if oldHeader is not None and oldHeader.streamId != header.streamId:
            stream = self.protocol.getStream(oldHeader.streamId)

            stream.channelUnregistered(channel)

        stream = self.protocol.getStream(header.streamId)
        stream.channelRegistered(channel)


class ChannelContext(object):
    """
    Provides contextual meta data for each channel attached to L{Encoder}.

    @ivar buffer: Any data from the channel waiting to be encoded.
    @type buffer: L{util.BufferedByteStream}
    @ivar header: The last header that was written to the stream.
    @type header: L{interfaces.IHeader}
    @ivar channel: The underlying RTMP channel.
    @type channel: L{interfaces.IChannel}
    @ivar encoder: The RTMP encoder object.
    @type encoder: L{Encoder}
    @ivar active: Whether this channel is actively producing data.
    @type active: C{bool}
    @ivar bytes: Number of frame bytes fetched by
    """

    def __init__(self, channel, encoder):
        self.channel = channel
        self.encoder = encoder
        self.buffer = util.BufferedByteStream()
        self.header = None

        self.queue = []
        self.currentPacket = None
        self.debug = rtmp.DEBUG

    def reset(self, header):
        """
        Called to reset the context when the channel has been reappropriated.
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'reset, bufferlen:%d, header:%r' % (
                len(self.buffer), header))

        self.buffer.truncate()
        self.bytes = 0
        self.bytesRequired = header.bodyLength

    def getFrame(self):
        """
        Called by the encoder to return any data that may be available in the
        C{buffer}. If a frames worth of data cannot be satisified then C{None}
        is returned. If a frame is ready then the buffer is updated
        accordingly and the bytes are returned.

        @return: The frame content bytes
        @rtype: C{str}
        """
        length = self.getMinimumFrameSize()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'length expected:%d, buffer length:%d' % (
                length, len(self.buffer)))

        if length == 0:
            return None

        self.buffer.seek(0)

        try:
            data = self.buffer.read(length)
        except IOError:
            return None

        self.buffer.consume()
        self.bytes += len(data)

        if self.bytes == self.bytesRequired:
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'complete body')

            if self.currentPacket:
                d, self.currentPacket = self.currentPacket, None
                d.addCallback(self.runQueue)

                reactor.callLater(0, d.callback, None)

        return data

    def getRelativeHeader(self):
        """
        Returns a header based on the last absolute header written to the
        stream and the channel's header. If there was no header written to the
        stream then the channel's header is returned.

        @rtype: L{interfaces.IHeader}
        """
        if self.header is None:
            return self.channel.getHeader()

        return _header.diffHeaders(self.header, self.channel.getHeader())

    def getMinimumFrameSize(self):
        """
        Returns the minimum number of bytes required to complete a frame.

        @rtype: C{int}
        """
        bytesLeft = self.bytesRequired - self.bytes
        frameSize = self.encoder.frameSize

        available = min(bytesLeft, frameSize)

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'minimum frame = %d' % (available,))

        if available < 0:
            raise RuntimeError('getMinimumFrameSize wanted to return %r' % (
                available,))

        return available

    def syncHeader(self):
        """
        Called to synchronise the contexts header with the channels.
        """
        self.header = self.channel.getHeader()

    def runQueue(self, result):
        """
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'runQueue length:%r, currentPacket:%r' % (
                len(self.queue), self.currentPacket))

        header, payload = None, None

        try:
            header, payload, d = self.queue[0]
            self.currentPacket = d
            del self.queue[0]
        except IndexError:
            pass

        if header is not None:
            self.channel.setHeader(header)
            self.channel.dataReceived(payload)

        return result

    # interfaces.IChannelObserver

    def dataReceived(self, data):
        """
        Called by the channel when data becomes available. Data is appended to
        the L{buffer} and if the channel is activated if it is not already.

        @param data: The chunk of data received.
        @type data: C{str}
        """
        self.buffer.append(data)

        self.encoder.activateChannel(self.channel)

    def headerChanged(self, header):
        """
        Called when the header has changed on the channel. Note that only
        relative header changes are notified.

        @param header: The new absolute header for the channel.
        @type header: L{interfaces.IHeader}
        """
        self.bytesRequired = header.bodyLength

    def bodyComplete(self):
        """
        Called by the channel when it's payload requirements have been
        satisfied.

        @note: This is a noop.
        """
        self.header = None


class Encoder(BaseCodec):
    """
    Interlaces all active channels to form one stream. At this point no
    attempt has been made to prioritise other channels over others.

    @ivar channelContext: A C{dict} of {channel: L{ChannelContext}} objects.
    @type channelContext: C{dict}
    @ivar scheduler: An RTMP channel scheduler. This composition allows
        different scheduler strategies without 'infecting' this class.
    @type scheduler: L{interfaces.IChannelScheduler}
    """

    def __init__(self, protocol):
        BaseCodec.__init__(self, protocol)

        self.channelContext = {}
        self.consumer = None
        self.scheduler = None
        self.debug = rtmp.DEBUG

    def registerScheduler(self, scheduler):
        """
        Registers a RTMP channel scheduler for the encoder to use when
        determining which channel to encode next.

        @param scheduler: The scheduler to register.
        @type scheduler: L{IChannelScheduler}
        """
        self.scheduler = scheduler

    def getJob(self):
        """
        @see: L{BaseCodec.getJob}
        """
        return self.encode

    def registerConsumer(self, consumer):
        """
        Registers a consumer that will be the recipient of the encoded rtmp
        stream.
        """
        self.consumer = consumer

    def createChannel(self, channelId):
        """
        """
        channel = BaseCodec.createChannel(self, channelId)

        context = self.channelContext[channel] = ChannelContext(channel, self)
        channel.registerObserver(context)

        return channel

    def activateChannel(self, channel):
        """
        Flags a channel as actively producing data.
        """
        BaseCodec.activateChannel(self, channel)

        channelId = self.channels[channel]

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Activating channel %d' % (channelId,))

        try:
            self.scheduler.activateChannel(channel)
        except IndexError:
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Scheduler reports already active')

    def deactivateChannel(self, channel):
        """
        Flags a channel as not actively producing data.
        """
        BaseCodec.deactivateChannel(self, channel)

        channelId = self.channels[channel]

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Dectivating channel %d' % (channelId,))


        context = self.channelContext[channel]
        self.scheduler.deactivateChannel(channel)

    def initialiseChannel(self, channel, oldHeader):
        """
        """
        BaseCodec.initialiseChannel(self, channel, oldHeader)

        header = channel.getHeader()
        context = self.channelContext[channel]

        context.reset(header)

    def writeFrame(self, context):
        """
        Writes an RTMP header and body to L{buffer}, if there is enough data
        available.

        @param context: The channel context from which to write a frame.
        @type context: L{ChannelContext}
        """
        channel = context.channel
        bytes = context.getFrame()

        if bytes is None:
            self.deactivateChannel(channel)

            return

        _header.encodeHeader(self.buffer, context.getRelativeHeader())

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Writing %d bytes to the buffer' % (len(bytes),))

        self.buffer.write(bytes)

        # reset the context to the latest absolute header from the channel
        # so that any changes that occur next time get picked up
        context.syncHeader()

    def encode(self):
        """
        Called to encode an RTMP frame (header and body) and write the result
        to the C{consumer}. If there is nothing to do then L{pause} will be
        called.
        """
        channel = self.scheduler.getNextChannel()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Encode: next channel %r' % (channel,))

        if channel is None:
            self.pause()

            return

        self.writeFrame(self.channelContext[channel])

        if len(self.buffer) > 0:
            self.consumer.write(self.buffer.getvalue())

            self.buffer.truncate(0)

    def writePacket(self, channelId, payload, streamId=None, datatype=None,
        timestamp=None):
        """
        Writes or queues a packet of data to the relevant channel.

        @param channelId: The channel id to write the payload to.
        @type channelId: C{int}
        @param payload: The payload to write to the channel.
        @type payload: C{str}
        @param streamId: The stream id to write the payload to.
        @type streamId: C{int} or C{None} to use the stream already assigned
            to the channel.
        @param datatype: The type of data the payload represents. See
            L{rtmpy.rtmp.event} for a list of possible values
        @type datatype: C{int} or C{None} to use the datatype already assigned
            to the channel.
        @param timestamp: The timestamp to assign to the channel.
        @type timestamp: C{int} or C{None} to use the timestamp already
            assigned to the channel.
        @raise ChannelError: An attempt to write relative values (C{None}) to
            the channel when there was no previous value.
        @return: A deferred whose callback will be fired when the complete
            packet is written to the channel buffer. This is not a guarantee
            that the data has been written to the consumer.
        @rtype: L{defer.Deferred}
        """
        channel = self.getChannel(channelId)
        oldHeader = channel.getHeader()

        kwargs = {
            'channelId': channelId,
            'streamId': streamId,
            'datatype': datatype,
            'bodyLength': len(payload),
            'timestamp': timestamp
        }

        header = _header.Header(**kwargs)

        if oldHeader is None and header.relative:
            raise ChannelError('Tried to write a relative header to an '
                'initialised channel (header:%r, channel:%r)' % (
                    header, channel))

        d = defer.Deferred()
        context = self.channelContext[channel]

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Writing packet header:%r' % (header,))
            rtmp.log(self, 'queue length:%d, currentPacket:%r' % (
                len(context.queue), context.currentPacket))

        if len(context.queue) == 0 and context.currentPacket is None:
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Writing packet immediately')

            channel.setHeader(header)
            channel.dataReceived(str(payload))

            context.currentPacket = d

            return
        else:
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Queuing packet')

            context.queue.append((header, payload, d))

            if context.currentPacket is None:
                context.runQueue(None)

        self.activateChannel(channel)

        return d


class FrameReader(object):
    """
    A generator object that decodes RTMP frames from a data stream. Feed it data
    via L{send} and then iteratively call L{next}.

    A frame consists of a header and then a chunk of data. Each header will
    contain the channel that the frame is destined for. RTMP allows multiple
    channels to be interleaved together.

    @ivar frameSize: The maximum size for an individual frame. Read-only, use
        L{setFrameSize} instead.
    @ivar stream: The underlying buffer containing the raw bytes.
    @type stream: L{BufferedByteStream}
    @ivar channels: A L{dict} of L{Channel} objects that are awaiting data.
    """

    frameSize = 128

    def __init__(self, stream=None):
        self.stream = stream or BufferedByteStream()
        self.channels = {}

    def setFrameSize(self, size):
        """
        Set the size of the next frame to be read.
        """
        self.frameSize = size

        for channel in self.channels.values():
            channel.frameSize = size

    def readHeader(self):
        """
        Reads an RTMP header from the stream.

        @rtype: L{_header.Header}
        """
        return _header.decodeHeader(self.stream)

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

        channel = self.channels[channelId] = Channel(self, self.stream)

        return channel

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

        if meta.datatype in event.STREAMABLE_TYPES:
            # don't buffer the data, pass it right on through
            return data, meta

        if complete:
            data = self.bucket.pop(meta.channelId, '') + data

            return data, meta

        channelId = meta.channelId

        self.bucket[channelId] = self.bucket.get(channelId, '') + data

        # nothing was available
        return None, None
