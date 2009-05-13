# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Channel type declarations.
"""

from twisted.internet import defer, threads
from zope.interface import implements
import pyamf

from rtmpy.util import BufferedByteStream
from rtmpy.rtmp import interfaces


#: Changes the frame size for events
FRAME_SIZE = 0x01
# 0x02 is unknown
#: Send every x bytes read by both sides
BYTES_READ = 0x03
#: A stream control message, has subtypes
CONTROL = 0x04
#: The servers downstream bandwidth
SERVER_BANDWIDTH = 0x05
#: The clients upstream bandwidth
CLIENT_BANDWIDTH = 0x06
#: Packet containing audio
AUDIO_DATA = 0x07
#: Packet containing video data
VIDEO_DATA = 0x08
# 0x0a - 0x0e is unknown
#: Shared object with variable length
FLEX_SHARED_OBJECT = 0x10
#: Shared message with variable length
FLEX_MESSAGE = 0x11
#: An invoke which does not expect a reply
NOTIFY = 0x12
#: Has subtypes
SHARED_OBJECT = 0x13
#: Like remoting call, used for stream actions too
INVOKE = 0x14
# 0x15 anyone?
#: FLV data
FLV_DATA = 0x16


class BaseError(Exception):
    """
    Base error class for all things `event`.
    """


class DecodeError(BaseError):
    """
    Base error class for decoding RTMP events.
    """


class TrailingDataError(DecodeError):
    """
    Raised if decoding an event does not consume the whole buffer.
    """


class EncodeError(BaseError):
    """
    Base error class for encoding RTMP events.
    """


class BaseEvent(object):
    """
    An abstract class that all event types must extend.
    """

    implements(interfaces.IEvent)

    def encode(self, buf):
        raise NotImplementedError()

    def decode(self, buf):
        raise NotImplementedError()

    def dispatch(self, listener):
        raise NotImplementedError()


class FrameSize(BaseEvent):
    """
    A frame size event. This determines the number of bytes for the frame
    body in the RTMP stream.

    @ivar size: Number of bytes for RTMP frame bodies.
    @type size: C{int}
    """

    def __init__(self, size=None):
        self.size = size

    def decode(self, buf):
        """
        Decode a frame size event.
        """
        self.size = buf.read_ulong()

    def encode(self, buf):
        """
        Encode a frame size event.
        """
        if self.size is None:
            raise EncodeError('Frame size not set')

        try:
            buf.write_ulong(self.size)
        except TypeError:
            raise EncodeError('Frame size wrong type '
                '(expected int, got %r)' % (type(self.size),))


class BytesRead(BaseEvent):
    """
    Number of bytes read?
    """

    def __init__(self, size=None):
        self.size = size

    def decode(self, buf):
        """
        Decode a bytes read event.
        """
        self.size = buf.read_ulong()

    def encode(self, buf):
        """
        Encode a bytes read event.
        """
        if self.size is None:
            raise EncodeError('Bytes read not set')

        try:
            buf.write_ulong(self.size)
        except TypeError:
            raise EncodeError('Bytes read wrong type '
                '(expected int, got %r)' % (type(self.size),))


class ControlEvent(BaseEvent):
    """
    A control event. Akin to Red5's Ping Event.
    """

    UNDEFINED = -1
    PING = 6
    PONG = 7

    def __init__(self, type=None, value1=0, value2=UNDEFINED, value3=UNDEFINED):
        self.type = type
        self.value1 = value1
        self.value2 = value2
        self.value3 = value3

    def __repr__(self):
        return '<%s type=%r value1=%r value2=%r value3=%r at 0x%x>' % (
            self.__class__.__name__, self.type, self.value1, self.value2,
            self.value3, id(self))

    def encode(self, buf):
        if self.type is None:
            raise EncodeError('Unknown control type (type:%r)' % (
                self.type,))

        try:
            buf.write_short(self.type)
        except TypeError:
            raise EncodeError('TypeError encoding type '
                '(expected int, got %r)' % (type(self.type),))

        try:
            buf.write_long(self.value1)
        except TypeError:
            raise EncodeError('TypeError encoding value1 '
                '(expected int, got %r)' % (type(self.value1),))

        try:
            buf.write_long(self.value2)
        except TypeError:
            raise EncodeError('TypeError encoding value2 '
                '(expected int, got %r)' % (type(self.value2),))

        try:
            buf.write_long(self.value3)
        except TypeError:
            raise EncodeError('TypeError encoding value3 '
                '(expected int, got %r)' % (type(self.value3),))

    def decode(self, buf):
        self.type = buf.read_short()
        self.value1 = buf.read_long()
        self.value2 = buf.read_long()
        self.value3 = buf.read_long()


class ServerBandwidth(BaseEvent):
    """
    A server bandwidth event.
    """

    def __init__(self, bandwidth=None):
        self.bandwidth = bandwidth

    def decode(self, buf):
        """
        Decode a server bandwidth event.
        """
        self.bandwidth = buf.read_ulong()

    def encode(self, buf):
        """
        Encode a server bandwidth event.
        """
        if self.bandwidth is None:
            raise EncodeError('Server bandwidth not set')

        try:
            buf.write_ulong(self.bandwidth)
        except TypeError:
            raise EncodeError('Server bandwidth wrong type '
                '(expected int, got %r)' % (type(self.bandwidth),))


class ClientBandwidth(BaseEvent):
    """
    A server bandwidth event.
    """

    def __init__(self, bandwidth=None, extra=None):
        self.bandwidth = bandwidth
        self.extra = extra

    def decode(self, buf):
        """
        Decode a client bandwidth event.
        """
        self.bandwidth = buf.read_ulong()
        self.extra = buf.read_uchar()

    def encode(self, buf):
        """
        Encode a client bandwidth event.
        """
        if self.bandwidth is None:
            raise EncodeError('Client bandwidth not set')

        if self.extra is None:
            raise EncodeError('Client extra not set')

        try:
            buf.write_ulong(self.bandwidth)
        except TypeError:
            raise EncodeError('Client bandwidth wrong type '
                '(expected int, got %r)' % (type(self.bandwidth),))

        try:
            buf.write_uchar(self.extra)
        except TypeError:
            raise EncodeError('Client extra wrong type '
                '(expected int, got %r)' % (type(self.extra),))


class Notify(BaseEvent):
    """
    Stream notification event.
    """

    def __init__(self, name=None, id=None, *args):
        self.name = name
        self.id = id
        self.argv = args

    def __repr__(self):
        return '<%s name=%r id=%r argv=%r at 0x%x>' % (
            self.__class__.__name__, self.name, self.id, self.argv, id(self))

    def encode(self, buf, encoding=pyamf.AMF0):
        def _encode():
            encoder = pyamf.get_encoder(encoding)
            encoder.stream = buf

            for e in [self.name, self.id]:
                encoder.writeElement(e)

            for e in self.argv:
                encoder.writeElement(e)

        return threads.deferToThread(_encode)

    def decode(self, buf, encoding=pyamf.AMF0):
        def _decode():
            decoder = pyamf.get_decoder(encoding)
            decoder.stream = buf

            for a in ['name', 'id']:
                setattr(self, a, decoder.readElement())

            self.argv = []

            while not buf.at_eof():
                self.argv.append(decoder.readElement())

        return threads.deferToThread(_decode)


class Invoke(Notify):
    """
    Similar to L{Notify} but a reply is expected.
    """

    def dispatch(self, listener):
        return listener.onInvoke(self)


class AudioData(BaseEvent):
    """
    A event containing audio data.
    """

    implements(interfaces.IStreamable)

    def __init__(self, data=None):
        self.data = data

    def decode(self, buf):
        """
        Decode an audio event.
        """
        self.data = buf.read()

    def encode(self, buf):
        """
        Encode an audio event.
        """
        if self.data is None:
            raise EncodeError('No audio data set')

        try:
            buf.write(self.data)
        except TypeError:
            raise EncodeError('Audio data wrong type '
                '(expected str, got %r)' % (type(self.data),))


class VideoData(BaseEvent):
    """
    A event containing video data. The event has no other idea of the data
    or even if it is valid ..
    """

    implements(interfaces.IStreamable)

    def __init__(self, data=None):
        self.data = data

    def decode(self, buf):
        """
        Decode an audio event.
        """
        self.data = buf.read()

    def encode(self, buf):
        """
        Encode a video event. 
        """
        if self.data is None:
            raise EncodeError('No video data set')

        try:
            buf.write(self.data)
        except TypeError:
            raise EncodeError('Video data wrong type '
                '(expected str, got %r)' % (type(self.data),))


TYPE_MAP = {
    FRAME_SIZE: FrameSize,
    BYTES_READ: BytesRead,
    CONTROL: ControlEvent,
    SERVER_BANDWIDTH: ServerBandwidth,
    CLIENT_BANDWIDTH: ClientBandwidth,
    NOTIFY: Notify,
    INVOKE: Invoke,
    AUDIO_DATA: AudioData,
    VIDEO_DATA: VideoData
}


def decode(datatype, body, *args, **kwargs):
    """
    A helper method that decodes a byte stream to an L{interfaces.IEvent}
    instance.

    @param datatype: The type of the event.
    @type datatype: C{int}
    @param body: The byte string holding the encoded form of the event.
    @return: A deferred, whose callback will return the event instance.
    @rtype: L{defer.Deferred} that contains a {interfaces.IEvent} instance
        corresponding to C{datatype}
    @raise DecodeError: The datatype is not known.
    @raise TrailingDataError: Raised if the body was not completely decoded.
    @note: This function doesn't actually raise the exceptions, they are
        wrapped by the deferred.
    """
    def _decode():
        if datatype not in TYPE_MAP:
            raise DecodeError('Unknown datatype \'%r\'' % (datatype,))

        buf = BufferedByteStream(body)
        # create an event instance
        event = TYPE_MAP[datatype]()

        def cb(res):
            # check here to ensure the whole buffer has been consumed
            if not buf.at_eof():
                raise TrailingDataError()

            return event

        d = defer.maybeDeferred(event.decode, buf, *args, **kwargs)

        return d.addCallback(cb)

    return defer.maybeDeferred(_decode)


def encode(event, *args, **kwargs):
    """
    A helper method that encodes an event.

    @param event: The event to be encoded.
    @type event: L{interfaces.IEvent}
    @return: A deferred, whose callback will return a tuple, the event
        datatype and the encoded event byte string.
    @rtype: L{defer.Deferred} that contains a tuple (C{int}, C{str})
    @raise EncodeError: If the event class does not correspond to a registered
        type.
    @raise TypeError: The event does not implement L{interfaces.IEvent}
    @note: This function doesn't actually raise the exceptions, they are
        wrapped by the deferred.
    """
    def _encode():
        if not interfaces.IEvent.providedBy(event):
            raise TypeError('Expected an event interface (got:%r)' % (
                type(event),))

        datatype = None
        kls = event.__class__

        for t, c in TYPE_MAP.iteritems():
            if c is kls:
                datatype = t

                break

        if datatype is None:
            raise EncodeError('Unknown event type for %r' % (event,))

        body = BufferedByteStream()

        def cb(res):
            return datatype, body.getvalue()

        d = defer.maybeDeferred(event.encode, body, *args, **kwargs)

        return d.addCallback(cb)

    return defer.maybeDeferred(_encode)


def get_type_class(type):
    """
    """
    return TYPE_MAP[type]
