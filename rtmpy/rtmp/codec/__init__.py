# -*- test-case-name: rtmpy.tests.test_codec -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP codecs. Encoders and decoders for rtmp streams.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

from twisted.internet import task
from zope.interface import implements

from rtmpy import rtmp, util
from rtmpy.rtmp import interfaces
from rtmpy.rtmp.codec import header as _header


MAX_CHANNELS = 64
FRAME_SIZE = 128


class DecodeError(rtmp.BaseError):
    """
    Raised if there is an error decoding an RTMP bytestream.
    """


class EncodeError(rtmp.BaseError):
    """
    Raised if there is an error encoding an RTMP bytestream.
    """


class NoManagerError(rtmp.BaseError):
    """
    Raised if an operation performed on a channel requires a registered
    manager.
    """


class Channel(object):
    """
    Acts as a container for an RTMP channel. Does not know anything of
    encoding or decoding channels, it is literally meant as a proxy between
    the byte stream and an observer.

    @ivar manager: The manager for this channel. The channel will report back
        to the manager about various activities it is performing.
    @type manager: L{interfaces.IChannelManager}
    @ivar header: The calculated header for this channel. RTMP can send
        relative headers, which will be merged with the previous headers to
        calculate the absolute values for the header.
    @type header: L{interfaces.IHeader} or C{None}
    @ivar frameRemaining: The amount of data that needs to be received before
        a frame can be considered complete.
    @type frameRemaining: C{int}
    @ivar buffer: Any buffered data before an observer was registered.
    @type buffer: C{str} or C{None}
    """

    implements(interfaces.IChannel)

    def __init__(self):
        self.manager = None
        self.header = None
        self.buffer = None
        self.observer = None

        self.debug = rtmp.DEBUG

    def registerManager(self, manager):
        """
        Registers a manager to this channel. The channel will L{reset} itself
        when a manager is registered.

        @param manager: The manager to register to this channel.
        @type manager: L{interfaces.IChannelManager}
        """
        if not interfaces.IChannelManager.providedBy(manager):
            raise TypeError('Expected IChannelManager for manager ' \
                '(got %s)' % (type(manager),))

        self.manager = manager
        self.reset()

    def registerObserver(self, observer):
        """
        Registers an observer to this channel. If there is any buffered data,
        the observer will be notified immediately.

        @param observer: The observer for this channel.
        @type observer: L{interfaces.IChannelObserver}
        """
        if not interfaces.IChannelObserver.providedBy(observer):
            raise TypeError('Expected IChannelObserver for observer ' \
                '(got %s)' % (type(observer),))

        self.observer = observer

        if self.buffer is not None:
            self.observer.dataReceived(self.buffer)
            self.buffer = None

    def reset(self):
        """
        Called to reset the channel's context.

        @note: Does not reset any header information that may already be
            applied to this channel.
        @raise ChannelError: If no manager has been registered.
        """
        if self.manager is None:
            raise NoManagerError('Resetting a channel requires a ' \
                'registered manager')

        self.frameRemaining = self.manager.frameSize
        self.frames = 0
        self.bytes = 0
        self.buffer = None
        self.observer = None
        self.bodyRemaining = None

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
        header then the new header must be absolute (relative=True). Otherwise
        the new values will be applied to the existing header. Setting the
        header requires a registered manager.

        @param header: The header to apply to this channel.
        @type header: L{interfaces.IHeader}
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'setHeader(%s)' % (header,))

        # this method is going to be called a lot - is this strictly
        # necessary?
        if not interfaces.IHeader.providedBy(header):
            raise TypeError("Expected header to implement IHeader")

        if self.manager is None:
            raise NoManagerError(
                'Setting the header requires a registered manager')

        if self.header is None:
            if header.relative is True:
                raise _header.HeaderError(
                    'Tried to set a relative header as absolute')
        else:
            if header.channelId != self.header.channelId:
                raise _header.HeaderError('Tried to assign a header from a '
                    'different channel (original:%d, new:%d)' % (
                        self.header.channelId, header.channelId))

        if header.relative is False:
            old_header, self.header = self.header, header

            if old_header is None:
                self.manager.initialiseChannel(self)
        else:
            # this stops a circular import error
            from rtmpy.rtmp.codec.header import mergeHeaders

            self.header = mergeHeaders(self.header, header)

        self.bodyRemaining = self.header.bodyLength - self.bytes

    def _write(self, data):
        """
        If an observer is registered then L{IChannelObserver.dataReceived} is
        called, otherwise the data is buffered until an observer is
        registered.
        """
        if self.observer is not None:
            self.observer.dataReceived(data)

            return

        if self.buffer is None:
            self.buffer = ''

        self.buffer += data

    def _adjustFrameRemaining(self, l):
        """
        Adjusts the C{frames} and C{frameRemaining} attributes based on the
        supplied length C{l}.
        """
        size = self.manager.frameSize

        while l >= size:
            self.frames += 1
            l -= size

        if l >= self.frameRemaining:
            self.frames += 1
            l -= self.frameRemaining
            self.frameRemaining = size

        self.frameRemaining -= l

    def dataReceived(self, data):
        """
        Called when a frame or partial frame is read from or written to the
        RTMP byte stream.

        @param data: A string of bytes.
        @type data: C{str}
        """
        if self.header is None:
            raise _header.HeaderError("Cannot write to a channel with no header")

        l = len(data)

        if self.bodyRemaining - l < 0:
            raise OverflowError('Attempted to write more data than was ' \
                'expected (attempted:%d remaining:%d total:%d)' % (
                    l, self.bodyRemaining, self.bytes + self.bodyRemaining))

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Received %d bytes' % (l,))

        self._write(data)

        self.bytes += l
        self.bodyRemaining -= l

        if self.bodyRemaining == 0:
            self.onComplete()

        self._adjustFrameRemaining(l)

    def onComplete(self):
        """
        Called when the channel has receieved the correct amount of data.
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'body completed')

        if self.manager is None:
            raise NoManagerError('A registered manager is required to '
                'complete a channel')

        self.manager.channelComplete(self)

        if self.observer:
            self.observer.bodyComplete()

        self.reset()

    def __repr__(self):
        s = []
        attrs = ['frameRemaining', 'frames', 'bytes', 'bodyRemaining']

        if self.header is None:
            s.append('header=None')
        else:
            s.append('channelId=%d' % (self.header.channelId,))
            s.append('datatype=%d' % (self.header.datatype,))

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
    @ivar channels: A list of channels.
    @type channels: C{dict} of L{Channel}
    @ivar frameSize: The number of bytes for each frame content.
    @type frameSize: C{int}
    """

    implements(interfaces.IChannelManager)

    channel_class = Channel

    def __init__(self):
        self.channels = {}
        self.deferred = None
        self.frameSize = FRAME_SIZE

        self.buffer = util.BufferedByteStream()
        self.job = task.LoopingCall(self.getJob())

        self.debug = rtmp.DEBUG

    def __del__(self):
        if hasattr(self, 'job') and self.job.running:
            self.job.stop()

    def getJob(self):
        """
        Returns the method to be iteratively called to process the codec.

        This method is intended to be implemented by sub-classes.
        """
        raise NotImplementedError()

    def start(self, when=0):
        """
        Starts or resumes the job. If the job is already running (i.e. not
        stopped) then this is a noop.

        @return: The deferred from starting the job.
        @rtype: L{twisted.internet.defer.Deferred}
        """
        if self.job.running:
            return self.deferred

        self.deferred = self.job.start(when, now=False)

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Started job')

        return self.deferred

    def pause(self):
        """
        Pauses the codec. Called when the buffer is exhausted. If the job is
        already stopped then this is a noop.
        """
        if self.job.running:
            self.job.stop()
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

        channel = self.channels[channelId] = BaseCodec.channel_class()
        channel.registerManager(self)

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
        keys = self.channels.keys()

        if len(keys) == MAX_CHANNELS:
            raise OverflowError("No free channel")

        for count in xrange(0, MAX_CHANNELS):
            try:
                if keys[count] != count:
                    return count
            except IndexError:
                return count

            count += 1

    def channelComplete(self, channel):
        """
        Called when the body of the channel has been satisfied.
        """
        # more here

    def initialiseChannel(self, channel):
        """
        Called when a header has been applied to an inactive channel.
        """
        if channel.manager != self:
            raise ValueError("Cannot initialise a channel that isn\'t "
                "registered to this manager")

        channel.reset()

    def setFrameSize(self, size):
        self.frameSize = size

        for channel in self.channels.values():
            channel.frameRemaining = size


class Decoder(BaseCodec):
    """
    Decodes an RTMP stream. De-interlaces the channels and writes the frames
    to the individual buffers. The decoder has the power to pause itself, but
    not to start.

    @ivar currentChannel: The channel currently being decoded.
    @type currentChannel: L{interfaces.IChannel}
    """

    def __init__(self,):
        BaseCodec.__init__(self)

        self.currentChannel = None

    def getJob(self):
        return self.decode

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
                rtmp.log(self, 'Not enough data to read header. ' \
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

        if self.currentChannel.frames != frames:
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
                rtmp.log(self, 'Not enough buffer to read header ' \
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

    def decode(self):
        """
        Attempt to decode the buffer. If a successful frame was decoded from
        the stream then the decoded bytes are removed.
        """
        # start from the beginning of the buffer
        self.buffer.seek(0)

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Decode (tell:%d, length:%d)' % (
                self.buffer.tell(), len(self.buffer),))

        if not self.canContinue():
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Buffer exhausted')

            self.pause()

            return

        self._decode()

        # delete the bytes that have already been decoded
        self.buffer.consume()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Complete decode (buffer: length:%d)' % (
                len(self.buffer)))

    def dataReceived(self, data):
        """
        Adds data to the end of the stream. 
        """
        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'Received %d bytes' % (len(data),))

        self.buffer.seek(0, 2)
        self.buffer.write(data)

    def channelComplete(self, channel):
        """
        Called when the body of the channel has been satisfied.
        """
        BaseCodec.channelComplete(self, channel)

        self.currentChannel = None

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
        self.active = False
        self.header = None
        self.bytes = 0

        self.channel.registerConsumer(self)

    def write(self, data):
        """
        Called by the channel when data becomes available.
        """
        self.buffer.append(data)

        if not self.active:
            self.encoder.activateChannel(self.channel)
            self.active = True

    def _deactivate(self):
        self.encoder.deactivateChannel(self.channel)
        self.active = False

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

        if length == 0:
            self._deactivate()

            return

        self.buffer.seek(0)

        try:
            data = self.buffer.read(length)
        except IOError:
            self._deactivate()

            return None

        self.buffer.consume()
        self.bytes += length

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
        bytesLeft = self.channel.bytes - self.bytes
        frameSize = self.encoder.frameSize

        available = min(bytesLeft, frameSize)

        if available < 0:
            available = 0

        return available

    def syncHeader(self):
        """
        Called to syncronise the contexts header with the channels.
        """
        self.header = self.channel.getHeader()


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

    def __init__(self):
        BaseCodec.__init__(self)

        self.channelContext = {}
        self.consumer = None
        self.scheduler = None

    def registerScheduler(self, scheduler):
        """
        Registers a RTMP channel scheduler for the encoder to use when
        determining which channel to encode next.

        @param scheduler: The scheduler to register.
        @type scheduler: L{IChannelScheduler}
        """
        if not interfaces.IChannelScheduler.providedBy(scheduler):
            raise TypeError('Expected IChannelScheduler interface')

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

    def activateChannel(self, channel):
        """
        Flags a channel as actively producing data.
        """
        if not channel in self.channelContext:
            self.channelContext[channel] = ChannelContext(channel, self)

        self.channelContext[channel].active = True
        self.scheduler.activateChannel(channel)

    def deactivateChannel(self, channel):
        """
        Flags a channel as not actively producing data.
        """
        if not channel in self.channelContext:
            raise RuntimeError('Attempted to deactivate a non-existant ' + \
                'channel')

        self.channelContext[channel].active = False
        self.scheduler.deactivateChannel(channel)

    def writeFrame(self, context):
        """
        Writes an RTMP header and body to L{buffer}, if there is enough data
        available.

        @param context: The channel context from which to write a frame.
        @type context: L{ChannelContext}
        """
        if not context.active:
            return

        channel = context.channel
        bytes = context.getFrame()

        if bytes is None:
            return

        _header.encodeHeader(self.buffer, context.getRelativeHeader())
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

        if channel is None:
            self.pause()

            return

        self.writeFrame(self.channelContext[channel])

        if len(self.buffer) > 0:
            self.consumer.write(self.buffer.getvalue())

            self.buffer.truncate(0)
