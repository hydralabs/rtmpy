# -*- test-case-name: rtmpy.tests.test_rtmp -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is
primarily used to stream audio and video over the internet to
the U{Flash Player<http://en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be
U{AMF<http://osflash.org/documentation/amf>} or raw audio/video
data like found in U{FLV<http://osflash.org/flv>}. A single
connection is capable of multiplexing many NetStreams using
different channels. Within these channels packets are split up
into fixed size body chunks.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}

@since: 0.1.0
"""

import time, struct
from twisted.internet import reactor, protocol, defer, task
from twisted.python import log

import pyamf
from pyamf.util import hexdump

from rtmpy.dispatcher import EventDispatcher
from rtmpy import util

#: Default port 1935 is a registered U{IANA<http://iana.org>} port.
RTMP_PORT = 1935

#: First single byte in the handshake request.
HEADER_BYTE = '\x03'

#: The header can come in one of four sizes: 12, 8, 4, or 1
#: byte(s).
HEADER_SIZES = [12, 8, 4, 1]

HANDSHAKE_LENGTH = 1536
HANDSHAKE_SUCCESS = 'rtmp.handshake.success'
HANDSHAKE_FAILURE = 'rtmp.handshake.failure'
HANDSHAKE_TIMEOUT = 'rtmp.handshake.timeout'
DEFAULT_HANDSHAKE_TIMEOUT = 5.0 # seconds

PROTOCOL_ERROR = 'rtmp.protocol.error'

MAX_CHANNELS = 64

EVENT_CHUNK_SIZE = 'rtmp.event.chunk-size'
EVENT_BYTES_READ = 'rtmp.event.bytes-read'
EVENT_SERVER_BANDWIDTH = 'rtmp.event.server-bandwidth'
EVENT_CLIENT_BANDWIDTH = 'rtmp.event.client-bandwidth'
EVENT_AUDIO_DATA = 'rtmp.event.audio-data'
EVENT_VIDEO_DATA = 'rtmp.event.video-data'
EVENT_INVOKE = 'rtmp.event.invoke'
EVENT_SHARED_OBJECT = 'rtmp.event.shared-object'

MAX_STREAMS = 0xffff

def _debug(obj, msg):
    print "%s<0x%x> - %s" %(obj.__class__.__name__, id(obj), msg)

def generate_handshake(uptime=None, ping=0):
    """
    Generates a handshake packet. If an C{uptime} is not supplied, it is figured
    out automatically.

    @see: U{Red5 mailinglist (external)
    <http://www.mail-archive.com/red5@osflash.org/msg04906.html>}
    """
    if uptime is None:
        uptime = util.uptime()

    handshake = struct.pack("!I", uptime) + struct.pack("!I", ping)

    x = uptime

    for i in range(0, (HANDSHAKE_LENGTH - 8) / 2):
        x = (x * 0xb8cd75 + 1) & 0xff
        handshake += struct.pack("!H", x << 8)

    return handshake

def decode_handshake(data):
    """
    Decodes a handshake packet into a C{tuple} (C{uptime}, C{ping}, C{data})

    @param data: C{str} or L{util.StringIO} instance
    """
    created = False

    if not isinstance(data, util.BufferedByteStream):
        data = util.BufferedByteStream(data)

        created = True

    data.seek(0)

    uptime = data.read_ulong()
    ping = data.read_ulong()
    body = data.read()

    if created:
        data.close()

    return uptime, ping, body

def read_header(channel, stream, byte_len):
    """
    Reads a header from the incoming stream.

    @param stream: The input buffer to read from.
    @type stream: L{BufferedByteStream}
    @type byte_len: C{int}
    """
    assert byte_len in HEADER_SIZES, 'Unexpected header size'

    if byte_len == 1:
        return

    channel.relative = byte_len != 12

    if byte_len >= 4:
        channel.timer = stream.read_24bit_uint()

    if byte_len >= 8:
        channel.length = stream.read_24bit_uint()
        channel.type = stream.read_uchar()

    if byte_len >= 12:
        channel.stream_id = stream.read_ulong()

def write_header(channel, stream, byte_len):
    assert byte_len in HEADER_SIZES, 'Unexpected header size'

    pos = HEADER_SIZES.index(byte_len)
    stream.write_uchar((pos << 6) | channel.channel_id)

    if byte_len == 1:
        return

    if byte_len >= 4:
        stream.write_24bit_uint(channel.timer)

    if byte_len >= 8:
        stream.write_24bit_uint(channel.length)
        stream.write_uchar(channel.type)

    if byte_len >= 12:
        stream.write_ulong(channel.stream_id)


class ChannelTypes:
    """
    RTMP Channel data types.
    """

    CHUNK_SIZE = 0x01
    # 0x02 is unknown
    BYTES_READ = 0x03
    PING = 0x04
    SERVER_BANDWIDTH = 0x05
    CLIENT_BANDWIDTH = 0x06
    AUDIO_DATA = 0x07
    VIDEO_DATA = 0x08
    # 0x0a - 0x0e is unknown
    # FLEX_SHARED_OBJECT = 0x10
    NOTIFY = 0x12
    SHARED_OBJECT = 0x13
    INVOKE = 0x14


class InvokeCommand:
    def __init__(self, channel, method, id, **kwargs):
        self.channel = channel
        self.stream = self.channel.stream
        self.method = method
        self.id = id
        self.kwargs = kwargs

    def __getitem__(self, n):
        return self.kwargs[n]

    def __setitem__(self, k, v):
        self.kwargs[k] = v

    def setResult(self, *args):
        self.result = args

    def complete(self):
        self.stream.onInvokeResult(self)


class RTMPStream:
    type_map = {
        ChannelTypes.INVOKE: 'onInvoke',
    }

    def __init__(self, manager, protocol):
        self.manager = manager
        self.channels = {}
        self.protocol = protocol
        self.pending_calls = {}

    def onInvoke(self, channel, method, id_, body):
        kw = {}
        for k, v in body.iteritems():
            kw[str(k)] = v

        obj = InvokeCommand(channel, method, id_, **kw)
        self.pending_calls[id_] = obj

        self.protocol.dispatchEvent(method, obj)
        #self.protocol.createChannel(self.protocol.getNextChannelId())

    def onInvokeResult(self, command):
        data = pyamf.encode('_result', command.id, *command.result).getvalue()
        channel = self.protocol.channel_manager.createChannel(command.channel.channel_id)
        channel.body.write(data)
        channel.body.seek(0)
        channel.type = ChannelTypes.INVOKE
        channel.stream_id = self.manager.getStreamId(self)
        channel.timer = 0
        channel.length = len(data)

        self.protocol.registerProducingChannel(channel)

    def registerChannel(self, channel):
        """
        Called when a channel is registered to this stream.
        """
        self.channels[channel.channel_id] = channel

    def dispatchPacket(self, channel, *args):
        # TODO nick - is this the right name?
        getattr(self, self.type_map[channel.type])(channel, *args)


class StreamManager:
    """
    Handles creation, deletion and general maintenance of registered streams.
    """

    def __init__(self, protocol, max_streams=MAX_STREAMS):
        self.protocol = protocol
        self.max_streams = min(max_streams, MAX_STREAMS)

        if self.max_streams < 1:
            raise ValueError, "max_streams cannot be less than 1"

        self._streams = {}
        self._rev_streams = {}

    def _checkRange(self, stream_id):
        if stream_id >= self.max_streams or stream_id < 0:
            raise IndexError, "stream index %d is out of range" % stream_id

    def getStreamId(self, stream):
        """
        Gets the id of registered stream.
        """
        return self._rev_streams[stream]

    def getStream(self, stream_id):
        """
        Gets a stream based on the id.
        """
        self._checkRange(stream_id)

        try:
            return self._streams[stream_id]
        except KeyError:
            raise KeyError("Unknown stream id %d" % stream_id)

    def closeStream(self, stream):
        """
        Closes a RTMP stream and removes it from t.

        @param stream: the stream to be closed.
        @type stream: L{RTMPStream}
        """
        try:
            idx = self._rev_streams[stream]
        except KeyError:
            raise KeyError("Unknown stream %r" % stream)

        del self._rev_streams[stream]
        del self._streams[idx] 

    def createStream(self, stream_id=None, **kwargs):
        """
        Creates a stream based on the C{stream_id}. If C{stream_id} is C{None}
        then it is calculated by L{getNextStreamId}.
        """
        if stream_id is None:
            stream_id = self.getNextStreamId()

        self._checkRange(stream_id)

        if stream_id in self._streams.keys():
            raise KeyError, "stream index %d already exists" % stream_id

        stream = self._streams[stream_id] = RTMPStream(self, self.protocol)
        self._rev_streams[stream] = stream_id

        return stream

    def removeStream(self, stream_id):
        """
        Removes a RTMP stream.

        @param stream_id: the index of the to stream be closed.
        @type stream_id: C{int}
        """
        self._checkRange(stream_id)

        stream = self._streams[stream_id]

        del self._streams[stream_id]
        del self._rev_streams[stream]

    def getNextStreamId(self):
        """
        Returns a free stream id.
        """
        keys = self._streams.keys()

        if len(keys) == self.max_streams:
            raise OverflowError("No free stream")

        count = 0

        while count < self.max_streams:
            try:
                if keys[count] != count:
                    return count
            except IndexError:
                return count

            count += 1

        return count


class ChannelDecoder:
    """
    Decodes the channel body and dispatches the relevant event to the attached
    stream.
    """

    type_map = {
        'chunk_size': ChannelTypes.CHUNK_SIZE,
        'server_bandwidth': ChannelTypes.SERVER_BANDWIDTH,
        'client_bandwidth': ChannelTypes.CLIENT_BANDWIDTH,
        'invoke': ChannelTypes.INVOKE,
    }

    encoding = pyamf.AMF0

    def chunk_size(self, channel):
        return channel.body.read_ulong()

    def server_bandwidth(self, channel):
        return channel.body.read_ulong()

    def client_bandwidth(self, channel):
        return channel.body.read_ulong(), channel.body.read_uchar()

    def invoke(self, channel):
        # should we be using threads here?
        name, id_, data = pyamf.decode(channel.body.getvalue(), encoding=self.encoding)

        return name, id_, data

    def __call__(self, channel):
        def cb(result):
            args = result

            if not isinstance(args, tuple):
                args = (args,)

            channel.stream.dispatchPacket(channel, *args)

        def eb(failure):
            log.err(failure)

        for key, t in self.type_map.iteritems():
            if t == channel.type:
                d = defer.maybeDeferred(getattr(self, key), channel)

                d.addErrback(eb).addCallback(cb)

                break
        else:
            raise NameError("Unknown type 0x%x" % channel.type)


class RTMPChannel:
    """
    @ivar read: Number of bytes read from the stream so far.
    @type read: C{int}
    @ivar chunk_remaining: A calculated field that returns the number of bytes
        required to complete the current chunk.
    @type chunk_remaining: C{int}
    @ivar length: Length of the channel body.
    @type length: C{int}
    @ivar timer: A timer value.
    @type timer: C{int}
    @ivar relative: If the timer value is relative
    @type relative: C{bool}
    @ivar type: The data type of channel.
    @type type: C{int}
    """

    read = 0

    def __init__(self, manager, protocol, channel_id, **kwargs):
        self.manager = manager
        self.protocol = protocol
        self.channel_id = channel_id

        self.body = util.BufferedByteStream()

        self.relative = kwargs.get('relative', False)
        self.length = kwargs.get('length', None)
        self.timer = kwargs.get('timer', None)
        self.type = kwargs.get('type', None)
        self.stream_id = kwargs.get('stream_id', None)
        self.stream = kwargs.get('stream', None)

    def _remaining(self):
        """
        Returns the number of bytes left to read from the stream.
        """
        return self.length - self.read

    remaining = property(_remaining)

    def write(self, data):
        data_len = len(data)

        if self.read + data_len > self.length:
            raise OverflowError, 'Attempted to write too much data to the body'

        self.read += data_len
        self.body.write(data)

        if self.read >= self.length:
            self.body.seek(0)
            if self.protocol.debug:
                _debug(self, "Dispatching %s" % ChannelManager.CHANNEL_COMPLETE)

            self.manager.dispatchEvent(ChannelManager.CHANNEL_COMPLETE, self)

    chunk_size = property(lambda self: self.protocol.chunk_size)

    def chunk_remaining(self):
        if self.read >= self.length - (self.length % self.chunk_size):
            return self.length - self.read

        return self.chunk_size - (self.read % self.chunk_size)

    chunk_remaining = property(chunk_remaining)

    def chunks_received(self):
        if self.length < self.chunk_size:
            if self.read == self.length:
                return 1

            return 0

        if self.length == self.read:
            return self.read / self.chunk_size + 1

        return self.read / self.chunk_size

    chunks_received = property(chunks_received)

    def __repr__(self):
        return '<%s.%s channel_id=%d @ 0x%x>' % (self.__module__,
            self.__class__.__name__, self.channel_id, id(self))


class ChannelManager(EventDispatcher):
    """
    Manages the creation/deletion and general maintenance of the channels
    linked to a connected RTMP Protocol. Also handles any events that channels
    may fire.

    @ivar protocol: The underlying protocol.
    @type:protocol: L{RTMPBaseProtocol}
    @ivar max_channels: The maximum number of simultaneous channels that is
        allowed. RTMP defines an absolute maximum of C{MAX_CHANNELS}.
    @type max_channels: C{int}
    @ivar _channels: A list of active channels
    @ivar _channels: C{dict} of L{RTMPChannel}
    """

    #: events
    CHANNEL_COMPLETE = 'channel.complete'

    def __init__(self, protocol, max_channels=MAX_CHANNELS):
        EventDispatcher.__init__(self)

        self.protocol = protocol
        self._channels = {}
        self.max_channels = min(max_channels, MAX_CHANNELS)

        if self.max_channels < 1:
            raise ValueError, "max_channels cannot be less than 1"

        self.addEventListener(ChannelManager.CHANNEL_COMPLETE, self.onCompleteBody)

    def getChannel(self, channel_id):
        """
        Gets an existing channel.

        @param channel_id: Index for the channel to retrieve.
        @type channel_id: C{int}
        @rtype: L{RTMPChannel}
        """
        if channel_id >= MAX_CHANNELS or channel_id < 0:
            raise IndexError, "channel index %d is out of range" % channel_id

        try:
            return self._channels[channel_id]
        except KeyError:
            raise KeyError, "channel %d not found" % channel_id

    def createChannel(self, channel_id=None):
        """
        Creates and returns a newly created channel. If C{channel_id} is
        C{None}, then it is calculated.

        @param channel_id: The channel index for the new channel.
        @type channel_id: C{int}

        @return: The newly created channel.
        @rtype: L{RTMPChannel}
        """
        if channel_id is None:
            channel_id = self.getNextChannelId()

        if channel_id >= self.max_channels or channel_id < 0:
            raise IndexError, "channel index %d is out of range" % channel_id

        if channel_id in self._channels.keys():
            raise KeyError, "channel index %d already exists" % channel_id

        channel = self._channels[channel_id] = RTMPChannel(self, self.protocol, channel_id)

        if self.protocol.debug:
            _debug(self, "Creating channel %d, %r" % (channel_id, channel))

        return channel

    def removeChannel(self, channel_id):
        """
        Removes a RTMP channel.

        @param: the index of the to channel be closed.
        @type: C{int}
        """
        if channel_id >= self.max_channels or channel_id < 0:
            raise IndexError, "channel index %d is out of range" % channel_id

        if self.protocol.debug:
            _debug(self, "Removing channel %d, %r" % (channel_id, self._channels[channel_id]))

        del self._channels[channel_id]

    def getNextChannelId(self):
        """
        Returns a free channel id.
        """
        keys = self._channels.keys()

        if len(keys) == self.max_channels:
            raise OverflowError("No free channel")

        count = 0

        while count < self.max_channels:
            try:
                if keys[count] != count:
                    return count
            except IndexError:
                return count

            count += 1

        return count

    def onCompleteBody(self, channel):
        """
        Called when a channel has received all of its data.
        
        @note: This may change to C{onData} at some point as we start to look
            at streaming larger chunks of data, e.g. video/audio.
        """
        self.removeChannel(channel.channel_id)


class BaseCodec:
    def __init__(self, protocol):
        self.protocol = protocol
        self.channel_manager = protocol.channel_manager
        self.stream_manager = protocol.stream_manager

        self.buffer = util.BufferedByteStream()

        self.channels = []
        self.channel_manager.addEventListener(ChannelManager.CHANNEL_COMPLETE,
            self._onChannelComplete)

    def start(self):
        if self.protocol.debug:
            _debug(self, "starting")

        if not self.job.running:
            if self.protocol.debug:
                _debug(self, "started")

            d = self.job.start(0)
            d.addErrback(lambda f: self.protocol.logAndDisconnect(f))

    def stop(self):
        if self.protocol.debug:
            _debug(self, "stopping")

        if self.job.running:
            self.job.stop()

            if self.protocol.debug:
                _debug(self, "stopped")

    def dataReceived(self, data):
        self.buffer.seek(0, 2)
        self.buffer.write(data)
        self.buffer.seek(0)

    def registerChannel(self, channel):
        self.channels.append(channel)

    def unregisterChannel(self, channel):
        self.channels.remove(channel)

    def _onChannelComplete(self, channel):
        """
        Called when a channel body has been completed. Attempt to decode the
        channel and dispatch to the relevant data type handler.
        """
        if channel in self.channels:
            self.channelComplete(channel)


class ProtocolDecoder(BaseCodec):
    def __init__(self, protocol):
        BaseCodec.__init__(self, protocol)

        self.job = task.LoopingCall(self.decode)
        self.channel_decoder = ChannelDecoder()
        self.current_channel = None

    def _decode(self):
        """
        Attempts to unweave the RTMP stream. Splits and unweave the frames and
        dispatch them to the relevant channel.
        """
        self.buffer.seek(0)

        stream = self.buffer

        if self.current_channel is not None:
            chunk_length = min(stream.remaining(),
                self.current_channel.chunk_remaining)

            num_chunks = self.current_channel.chunks_received

            if chunk_length > 0:
                if self.protocol.debug:
                    _debug(self, "Writing %d bytes to channel %r" % (
                        chunk_length, self.current_channel))

                self.current_channel.write(stream.read(chunk_length))

            if self.current_channel.chunks_received != num_chunks:
                if self.protocol.debug:
                    _debug(self, "Received full chunk")
                    print hexdump(self.current_channel.body.getvalue())

                self.current_channel = None

                return

        if stream.remaining() == 0:
            self.stop()

            return

        start_of_header = stream.tell()

        header_byte = stream.read_uchar()
        header_len = HEADER_SIZES[header_byte >> 6]

        if stream.remaining() < header_len - 1:
            # not enough stream left to continue decoding, rewind and wait
            if self.protocol.debug:
                _debug(self, "Insufficient data, rewinding (header_len:%d, stream_len:%d)" %(header_len, stream.remaining()))

            stream.seek(start_of_header)
            self.stop()

            return

        channel_id = header_byte & 0x3f
        try:
            self.current_channel = self.channel_manager.getChannel(channel_id)
        except KeyError:
            self.current_channel = self.channel_manager.createChannel(channel_id)
            self.registerChannel(self.current_channel)

        read_header(self.current_channel, stream, header_len)

        # compare headers here
        if header_len == 12:
            self.current_channel.stream = self.stream_manager.getStream(self.current_channel.stream_id)

    def decode(self):
        if self.protocol.debug:
            _debug(self, "Begin decoding stream buffer length: %d, channel: %r" % (len(self.buffer), self.current_channel))

        try:
            self._decode()
        except:
            self.protocol.logAndDisconnect()
        else:
            if self.protocol.debug:
                _debug(self, "End decoding stream pos: %d, remaining: %d, current_channel: %r" % (
                    self.buffer.tell(), self.buffer.remaining(), self.current_channel))

            self.buffer.consume()

    def channelComplete(self, channel):
        self.unregisterChannel(channel)

        self.channel_decoder(channel)


class ProtocolEncoder(BaseCodec):
    def __init__(self, protocol):
        BaseCodec.__init__(self, protocol)

        self.job = task.LoopingCall(self.encode)
        self.meta_channels = {}
        self.pos = 0

    def write(self, data):
        self.protocol.transport.write(data)

    def _encode(self):
        if len(self.channels) == 0:
            self.stop()

            return

        if self.pos >= len(self.channels):
            self.pos = 0

        channel = self.channels[self.pos]
        meta = self.meta_channels[channel]

        if meta['last_header'] is None:
            # send a full 12 byte header
            write_header(channel, self.buffer, 12)
            meta['last_header'] = channel
        else:
            write_header(channel, self.buffer, 1)

        chunk_length = min(channel.body.remaining(), channel.chunk_remaining, channel.chunk_size)
        self.buffer.write(channel.body.read(chunk_length))

        if channel.body.remaining() == 0:
            self.channelComplete(channel)

        self.pos += 1

    def encode(self):
        if self.protocol.debug:
            _debug(self, "Begin encoding; buffer length: %d" % len(self.buffer))

        try:
            self._encode()
            self.write(self.buffer.getvalue())
            self.buffer.truncate()
        except Exception, e:
            self.protocol.logAndDisconnect()
        else:
            if self.protocol.debug:
                _debug(self, "End encoding stream pos: %d, remaining: %d" % (
                    self.buffer.tell(), self.buffer.remaining()))

    def registerChannel(self, channel):
        BaseCodec.registerChannel(self, channel)

        self.meta_channels[channel] = {
            'last_header': None,
            'index': len(self.channels) - 1
        }

        self.start()

    def channelComplete(self, channel):
        self.unregisterChannel(channel)

    def unregisterChannel(self, channel):
        BaseCodec.unregisterChannel(self, channel)

        del self.meta_channels[channel]

class BaseProtocol(protocol.Protocol, EventDispatcher):
    """
    I provide the basis for the initial handshaking phase and decoding RTMP
    packets as they arrive.

    @ivar buffer: Contains any remaining unparsed data from the C{transport}.
    @type buffer: L{util.BufferedByteStream}
    @ivar state: The state of the protocol.
    @type state: C{str}
    @ivar channel_manager: Manages the channels.
    @type channel_manager: C{ChannelManager}
    @ivar current_channel: The channel that is currently being written to/read
        from.
    @type current_channel: L{RTMPChannel} or C{None}
    """

    chunk_size = 128

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    handshakeTimeout = DEFAULT_HANDSHAKE_TIMEOUT
    debug = False

    def connectionMade(self):
        if self.debug:
            _debug(self, "Connection made")

        protocol.Protocol.connectionMade(self)

        self.state = BaseProtocol.HANDSHAKE
        self.buffer = util.BufferedByteStream()
        self.my_handshake = None
        self.received_handshake = None

        # setup event observers
        self.addEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.addEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)

        self.setTimeout(self.handshakeTimeout,
            lambda: self.dispatchEvent(HANDSHAKE_TIMEOUT))

    def setTimeout(self, timeout, func):
        if self.debug:
            _debug(self, "Setting timeout: %s seconds" % timeout)

        if hasattr(self, '_timeout'):
            if not self._timeout.cancelled:
                self._timeout.cancel()

        self._timeout = reactor.callLater(timeout, func)

    def clearTimeout(self):
        if self.debug:
            _debug(self, "Clearing timeout")

        if not hasattr(self, '_timeout'):
            return

        if not self._timeout.cancelled and not self._timeout.called:
            if self.debug:
                _debug(self, "Cancelling timeout")
            self._timeout.cancel()

        del self._timeout

    def connectionLost(self, reason):
        """
        Called when the connection is lost for some reason.

        Cleans up any timeouts/buffer etc.
        """
        if self.debug:
            _debug(self, "Lost connection (reason:%s)" % reason)

        self.clearTimeout()
        self.channel_manager = None
        self.stream_manager = None

        if hasattr(self, 'decoder'):
            self.decoder.stop()
            self.decoder = None

        if hasattr(self, 'encoder'):
            self.encoder.stop()
            self.encoder = None

    def decodeHandshake(self, data):
        """
        Negotiates the handshake phase of the protocol. Needs to be implemented
        by the subclass.

        @see: U{RTMP handshake on OSFlash (external)
        <http://osflash.org/documentation/rtmp#handshake>} for more info.
        """
        raise NotImplementedError

    def decodeStream(self, data):
        self.decoder.dataReceived(data)
        self.decoder.start()

    def logAndDisconnect(self, failure=None):
        if self.debug:
            log.err()
            _debug(self, "error")

        self.transport.loseConnection()

        if self.debug:
            raise

    def dataReceived(self, data):
        """
        Called when data is received from the underlying transport. Splits the
        data stream into chunks and delivers them to each channel.
        """
        if self.debug:
            _debug(self, "Receive data: state=%s, len=%d, stream.len=%d, stream.pos=%d" % (
                self.state, len(data), len(self.buffer), self.buffer.tell()))

        try:
            if self.state == BaseProtocol.HANDSHAKE:
                self.decodeHandshake(data)
            elif self.state == BaseProtocol.STREAM:
                self.decodeStream(data)
        except:
            self.logAndDisconnect()

    def onHandshakeSuccess(self):
        """
        Called when the RTMP handshake was successful. Once this is called,
        packet streaming can commence.
        """
        self.state = BaseProtocol.STREAM
        self.removeEventListener(HANDSHAKE_SUCCESS, self.onHandshakeSuccess)
        self.removeEventListener(HANDSHAKE_FAILURE, self.onHandshakeFailure)
        self.my_handshake = None
        self.received_handshake = None
        self.clearTimeout()

        self.channel_manager = ChannelManager(self)
        self.stream_manager = StreamManager(self)

        self.decoder = ProtocolDecoder(self)
        self.encoder = ProtocolEncoder(self)

        self.core_stream = self.stream_manager.createStream(0, immutable=True)

    def onHandshakeFailure(self, reason):
        """
        Called when the RTMP handshake failed for some reason. Drops the
        connection immediately.
        """
        if self.debug:
            _debug(self, "Failed handshake (reason:%s)" % reason)
        self.transport.loseConnection()

    def onHandshakeTimeout(self):
        """
        Called if the handshake was not successful within
        L{self.handshakeTimeout} seconds. Disconnects the peer.
        """
        if self.debug:
            _debug(self, "Handshake timedout")
        self.transport.loseConnection()

    def registerProducingChannel(self, channel):
        self.encoder.registerChannel(channel)
