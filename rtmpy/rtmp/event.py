# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Channel type declarations.
"""

from twisted.internet import defer
from zope.interface import implements

from rtmpy.util import BufferedByteStream
from rtmpy.rtmp import interfaces


#: Changes the frame size for packets
FRAME_SIZE = 0x01
# 0x02 is unknown
#: Send every x bytes read by both sides
BYTES_READ = 0x03
#: Ping is a stream control message, has subtypes
PING = 0x04
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


class FrameSize(BaseEvent):
    """
    A frame size event. This determines the number of bytes for the frame body
    in the RTMP stream.
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
        buf.write_ulong(self.size)


TYPE_MAP = {
    FRAME_SIZE: FrameSize,
}


def decode(datatype, body):
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

        return defer.maybeDeferred(event.decode, buf).addCallback(cb)

    return defer.maybeDeferred(_decode)


def encode(event):
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

        return defer.maybeDeferred(event.encode, body).addCallback(cb)

    return defer.maybeDeferred(_encode)
