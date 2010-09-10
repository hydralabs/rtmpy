# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is primarily used
to stream audio and video over the internet to the U{Adobe Flash Player<http://
en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be U{AMF<http://osflash
.org/documentation/amf>} or raw audio/video data like found in U{FLV<http://
osflash.org/flv>}. A single connection is capable of multiplexing many
NetStreams using different channels. Within these channels packets are split up
into fixed size body chunks.

@see: U{RTMP<http://dev.rtmpy.org/wiki/RTMP>}
"""

from twisted.python import log, failure
from twisted.internet import protocol, task, defer
import pyamf
from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import message, codec
from rtmpy import exc


#: Maximum number of streams that can be active per RTMP stream
MAX_STREAMS = 0xffff


class RemoteCallFailed(failure.Failure):
    """
    """

_reg = {}


def expose(func):
    if hasattr(func, '__call__'):
        _reg[func.func_name] = func.func_name

        return func

    def decorator(f):
        _reg[func] = f.func_name

        return f

    return decorator


class Stream(object):

    def __init__(self, protocol, streamId):
        self.protocol = protocol
        self.streamId = streamId

        self.timestamp = 0
        self.lastInvokeId = -1
        self.activeInvokes = {}

    def reset(self):
        # TODO: check active invokes and errback
        self.timestamp = 0
        self.lastInvokeId = -1
        self.activeInvokes = {}

    def sendStatus(self, code, *args, **kwargs):
        """
        Informs the peer of a change of status.
        """
        kwargs.setdefault('level', 'status')
        kwargs['code'] = code

        if not args:
            args = (None,)

        msg = message.Invoke('onStatus', 0, *list(args) + [kwargs])

        self.sendMessage(msg)

    def setTimestamp(self, timestamp, relative=True):
        """
        Sets the timestamp for this stream. The timestamp is measured in
        milliseconds since an arbitrary epoch. This could be since the stream
        started sending or receiving audio/video etc.

        @param relative: Whether the supplied timestamp is relative to the
            previous.
        """
        if relative:
            self.timestamp += timestamp
        else:
            if timestamp < self.timestamp:
                raise ValueError('Cannot set a negative timestamp')

            self.timestamp = timestamp

    def sendMessage(self, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. This a low level method and is not
        part of any public api. If its use is necessary then this is a bug.

        @param msg: The RTMP message to be sent by this stream.
        @type: L{message.Message}
        @param whenDone: An optional callback that is fired once the complete
            encoded RTMP message has been sent to the peer. This is not the same
            as a U{defer.Deferred} instance. When called it receives no params.
        """
        self.protocol.sendMessage(self, msg, whenDone)

    def _handleInvokeResponse(self, result, id_):
        """
        Called to handle the response to an invoked method
        """
        if id_ == 0:
            return result

        d = self.activeInvokes.pop(id_, None)

        if d is None:
            self.sendMessage(message.Invoke('_error', id_, None, {}))

            raise RuntimeError('Missing activeInvoke for id %r' % (id_,))

        def write_error(fail):
            code = getattr(fail.type, 'code', 'NetConnection.Call.Failed')

            msg = message.Invoke('_error', id_, None, {
                'level': 'error',
                'code': code,
                'description': fail.getErrorMessage()
            })

            self.sendMessage(msg)

            return fail

        def write_result(result):
            # need to figure out how to set the first param
            msg = message.Invoke('_result', id_, None, result)

            self.sendMessage(msg)

            return result

        d.addCallbacks(write_result, write_error)

        return result

    def onInvoke(self, name, id_, args, timestamp):
        """
        Called when an invoke message has been received from the peer. This
        could be a request or a response depending on whether id_ is 'in use'.

        @return: A deferred containing the result of the invoke call. This is
            not strictly necessary but useful for testing purposes.
        @retype: L{defer.Deferred}
        """
        d = self.activeInvokes.pop(id_, None)

        if d:
            # handle the response
            if name == '_error':
                d.errback(RemoteCallFailed(args))
            elif name == '_result':
                d.callback(*args)
            else:
                log.msg('Unhandled name for invoke response %r' % (name,))

            return d

        d = defer.Deferred()

        # a request from the peer to call a local method
        try:
            func = self.getInvokableTarget(name)
        except:
            d.errback()
            func = None

        if len(args) == 1 and args[0] is None:
            args = args[1:]

        if func is None:
            if not d.called:
                d.errback(exc.CallFailed('Unknown method %r' % (name,)))
        else:
            d = defer.maybeDeferred(func, *args)

        if id_ > 0:
            self.activeInvokes[id_] = d

        d.addBoth(self._handleInvokeResponse, id_)

        return d

    def getInvokableTarget(self, name):
        """
        """
        func_name = _reg.get(name, None)

        if not func_name:
            return

        return getattr(self, func_name)

    def onNotify(self, *args):
        print 'notify', args

    def onAudioData(self, data, timestamp):
        pass

    def onVideoData(self, data, timestamp):
        pass

    def onFrameSize(self, size, timestamp):
        raise NotImplementedError

    def onDownstreamBandwidth(self, *args):
        raise NotImplementedError

    def onUpstreamBandwidth(self, *args):
        raise NotImplementedError

    def onControlMessage(self, *args):
        raise NotImplementedError

    def onBytesRead(self, *args):
        raise NotImplementedError

    @expose
    def publish(self, name, *args):
        c = self.protocol.getStream(0)
        c.sendMessage(message.ControlMessage(0, 1,))

        self.sendStatus('NetStream.Publish.Start',
            description='stream1283853804683 is now published.',
            clientid='CDAwMKFF')

        print 'published'

    @expose
    def closeStream(self):
        self.sendStatus('NetStream.Unpublish.Success',
            description='stream1283853804683 is now unpublished.',
            clientid='CDAwMKFF')

class ControlStream(Stream):
    """
    A privileged stream that can send and receive control messages as well as
    having greater integration with the underlying protocol

    @ivar decoder: L{codec.Decoder} instance owned by the protocol.
    @ivar encoder: L{codec.Encoder} instance owned by the protocol.
    """

    def __init__(self, protocol, streamId):
        Stream.__init__(self, protocol, streamId)

        self.decoder = self.protocol.decoder
        self.encoder = self.protocol.encoder

    def onFrameSize(self, size, timestamp):
        """
        Called when the peer sets its RTMP frame size

        @param size: The new size of any RTMP frames sent from the peer.
        @param timestamp: Time this message was received.
        """
        self.decoder.setFrameSize(size)

    def onDownstreamBandwidth(self, bandwidth, timestamp):
        """
        """

    def onUpstreamBandwidth(self, bandwidth, extra, timestamp):
        """
        """

    def onControlMessage(self, msg, timestamp):
        """
        """

    def onBytesRead(self, bytes, timestamp):
        """
        """

    @expose
    def createStream(self):
        return len(self.protocol.streams)

    @expose
    def deleteStream(self, streamId, foo):
        print streamId, foo


class DecodingDispatcher(object):
    """
    A proxy class that listens for events fired from the L{codec.Decoder}

    @param protocol: The L{RTMPProtocol} instance attached to the decoder.
    """

    def __init__(self, protocol):
        self.protocol = protocol

    def dispatchMessage(self, stream, datatype, timestamp, data):
        """
        Called when the RTMP decoder has read a complete RTMP message.

        @param stream: The L{Stream} to receive this mesage.
        @param datatype: The RTMP datatype for the message.
        @param timestamp: The absolute timestamp this message was received.
        @param data: The raw data for the message.
        """
        m = message.get_type_class(datatype)()

        m.decode(BufferedByteStream(data))

        m.dispatch(stream, timestamp)

    def bytesInterval(self, bytes):
        """
        Called when a specified number of bytes has been read from the stream.
        The RTMP protocol demands that we send an acknowledge message to the
        peer. If we don't do this, Flash will stop streaming video/audio.
        """
        stream = self.protocol.getStream(0)

        stream.sendMessage(message.BytesRead(self.protocol.decoder.bytes))


class EncodingDispatcher(object):
    """
    TODO: Figure out if we need this class to listen to the bytesInterval for
    encoding
    """

    def bytesInterval(self, bytes):
        pass


class RTMPProtocol(protocol.Protocol):
    """
    Provides basic handshaking and RTMP protocol support.

    @ivar state: The state of the protocol. Can be either C{HANDSHAKE} or
        C{STREAM}.
    @type state: C{str}
    @ivar objectEncoding: The version to de/encode AMF packets. Set via the
        connect packet.
    """

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    objectEncoding = pyamf.AMF0

    def logAndDisconnect(self, reason, *args, **kwargs):
        """
        Called when something fatal has occurred. Logs any errors and closes the
        connection.
        """
        # weirdly, if log.err is used - trial breaks?!
        log.msg(failure=reason)
        self.transport.loseConnection()

        return reason

    def connectionMade(self):
        """
        Called when this a connection has been made.
        """
        self.state = self.HANDSHAKE
        self.dataReceived = self._handshake_dataReceived

        self.handshaker = self.factory.buildHandshakeNegotiator(self)

        # TODO: apply uptime, version to the handshaker instead of 0, 0
        self.handshaker.start(0, 0)

    def connectionLost(self, reason):
        """
        Called when the connection has been lost.

        @param reason: The reason for the disconnection
        """
        if self.state == self.HANDSHAKE:
            try:
                del self.handshaker
            except:
                pass
        elif self.state == self.STREAM:
            if hasattr(self, 'application') and self.application:
                self.application.clientDisconnected(self, reason)

            if hasattr(self, 'decoder_task'):
                del self.decoder_task

            if hasattr(self, 'decoder'):
                del self.decoder

            if hasattr(self, 'encoder_task'):
                del self.encoder_task

            if hasattr(self, 'encoder'):
                del self.encoder

    def _stream_dataReceived(self, data):
        try:
            self.decoder.send(data)

            if self.decoder_task is None:
                self._startDecoding()
        except:
            self.logAndDisconnect(failure.Failure())

    def _handshake_dataReceived(self, data):
        try:
            self.handshaker.dataReceived(data)
        except:
            self.logAndDisconnect(failure.Failure())

    def _startDecoding(self):
        """
        Called to start asynchronously iterate the decoder.

        @return: A C{Deferred} which will kill the task once the decoding is
            done or on error will kill the connection.
        """
        def cullTask(result):
            self.decoder_task = None

            return result

        self.decoder_task = task.coiterate(self.decoder)

        self.decoder_task.addBoth(cullTask)
        self.decoder_task.addErrback(self.logAndDisconnect)

        return self.decoder_task

    def _startEncoding(self):
        """
        Called to start asynchronously iterate the encoder.

        @return: A C{Deferred} which will kill the task once the encoder is
            done or on error will kill the connection.
        """
        def cullTask(result):
            self.encoder_task = None

            return result

        self.encoder_task = task.coiterate(self.encoder)

        self.encoder_task.addBoth(cullTask)
        self.encoder_task.addErrback(self.logAndDisconnect)

        return self.encoder_task

    def handshakeSuccess(self, data):
        """
        Handshaking was successful, streaming now commences.

        @param data: Any data left over from the handshake negotiations.
        """
        self.state = self.STREAM

        self.dataReceived = self._stream_dataReceived
        del self.handshaker

        self.startStreaming()

        if data:
            self.dataReceived(data)

    def startStreaming(self):
        """
        Handshaking was successful, streaming now commences.
        """
        self.streams = {}
        self.application = None

        self.decoder = codec.Decoder(DecodingDispatcher(self), self)
        self.encoder = codec.Encoder(self.transport, EncodingDispatcher())

        self.decoder_task = None
        self.encoder_task = None

    # IStreamFactory
    def getStream(self, streamId):
        """
        Returns the L{Stream} instance related to the C{streamId}.

        An id of C{0} is special as it is considered the control stream.
        """
        s = self.streams.get(streamId, None)

        if s is None:
            if streamId == 0:
                s = self.factory.getControlStream(self, streamId)
            else:
                s = Stream(self, streamId)

            self.streams[streamId] = s

        return s

    def sendMessage(self, stream, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. Not part of a public api, use
        C{stream.sendMessage} instead.

        @param stream: The stream instance that is sending the message.
        @type stream: L{Stream}
        @param msg: The message being sent to the peer.
        @type msg: L{message.Message}
        @param whenDone: A callback fired when the message has been written to
            the RTMP stream. See L{Stream.sendMessage}
        """
        buf = BufferedByteStream()

        # this will probably need to be rethought as this could block for an
        # unacceptable amount of time. For most messages however it seems to be
        # fast enough and the penalty for setting up a new thread is too high.
        msg.encode(buf)

        self.encoder.send(buf.getvalue(), msg.RTMP_TYPE, stream.streamId,
            stream.timestamp, whenDone)

        if not self.encoder_task:
            self._startEncoding()
