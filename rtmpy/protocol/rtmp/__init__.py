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
from zope.interface import Interface, Attribute

from rtmpy.protocol.rtmp import message, codec
from rtmpy import exc


class IChannelMeta(Interface):
    """
    Contains meta data related to a channel.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    timestamp = Attribute("The relative time value for the associated message.")
    datatype = Attribute("The datatype for the corresponding channel.")
    bodyLength = Attribute("The length of the channel body.")
    streamId = Attribute("An C{int} representing the linked stream.")


#: Maximum number of streams that can be active per RTMP stream
MAX_STREAMS = 0xffff

#: A dictionary of
_exposed_funcs = {}


class RemoteCallFailed(failure.Failure):
    """
    """


def expose(func):
    """
    A decorator that provides an easy way to expose methods that the peer can
    'call' via RTMP C{invoke} or C{notify} messages.

    Example usage::

        @expose
        def someRemoteMethod(self, foo, bar):
            pass

        @expose('foo-bar')
        def anotherExposedMethod(self, *args):
            pass

    If expose is called with no args, the function name is used.
    """
    if hasattr(func, '__call__'):
        _exposed_funcs[func.func_name] = func.func_name

        return func

    def decorator(f):
        _exposed_funcs[func] = f.func_name

        return f

    return decorator


class ExtraResult(object):
    """
    """

    def __init__(self, result, extra=None):
        self.result = result
        self.extra = extra


class BaseStream(object):
    """
    """

    def __init__(self, streamId):
        self.streamId = streamId

        self.timestamp = 0
        self.lastInvokeId = -1
        self.activeInvokes = {}

    def reset(self):
        # TODO: check active invokes and errback
        self.timestamp = 0
        self.lastInvokeId = -1
        self.activeInvokes = {}

    def call(self, name, *args, **kwargs):
        whenDone = kwargs.get('whenDone', None)

        if not whenDone:
            self.sendMessage(message.Invoke(name, 0, None, *args))

            return

        self.lastInvokeId += 1
        invokeId = self.lastInvokeId

        d = defer.Deferred()
        m = message.Invoke(name, invokeId, None, *args)
        self.activeInvokes[invokeId] = d

        self.sendMessage(m, whenDone=whenDone)

        return d

    def sendStatus(self, code_or_status, command=None, **kwargs):
        """
        Informs the peer of a change of status.

        @param code_or_status: A status message or L{status.Status} instance.
            If a string is supplied it will be converted to an L{status.Status}.
        @param command: The command object part of the L{message.Invoke}
            message. Not quite sure what this achieves right now. Defaults to
            L{None}.
        @param kwargs: If a string status message is supplied then any extra
            kwargs will form part of the generated L{status.Status} message.
        """
        if isinstance(code_or_status, status.Status):
            status_obj = code_or_status
        else:
            status_obj = status.status(code_or_status, **kwargs)

        msg = message.Invoke('onStatus', 0, *[command, status_obj])

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
            if isinstance(result, ExtraResult):
                msg = message.Invoke('_result', id_, result.extra, result.result)
            else:
                msg = message.Invoke('_result', id_, None, result)

            self.sendMessage(msg)

            return result

        d.addCallbacks(write_result, write_error)

        return result

    def _callExposedMethod(self, name, *args):
        """
        Returns a L{defer.Deferred} that will hold the result of the called
        method.

        @param name: The name of the method to call
        @param args: The supplied args from the invoke/notify call.
        """
        d = defer.Deferred()

        # a request from the peer to call a local method
        try:
            func = self.getInvokableTarget(name)
        except:
            d.errback()

            return d

        if len(args) >= 1 and args[0] is None:
            args = args[1:]

        if func is None:
            d.errback(exc.CallFailed('Unknown method %r' % (name,)))
        else:
            d = defer.maybeDeferred(func, *args)

        return d

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

        d = self._callExposedMethod(name, *args)

        if id_ > 0:
            self.activeInvokes[id_] = d

        d.addBoth(self._handleInvokeResponse, id_)

        return d

    def onNotify(self, name, args, timestamp):
        """
        Call an exposed method on this peer but without regard to any return
        value.

        @param name: The name of the method to call
        @param args: A list of arguments for this method.
        @param timestamp: The timestamp at which this notify was called.
        """
        self._callExposedMethod(name, *args)


    def getInvokableTarget(self, name):
        """
        Used to match a callable based on the supplied name when a notify or
        invoke is encountered. Returns C{None} if not found.

        This allows fine grained control over what this stream can expose to the
        peer.

        @param name: The name of the function to be mapped to a callable.
        @return: A callable or C{None}
        """
        func_name = _exposed_funcs.get(name, None)

        if not func_name:
            return

        return getattr(self, func_name)


    def sendMessage(self, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. This a low level method and is not
        part of any public api. If its use is necessary then this is a bug.

        Must be implemented by subclasses.

        @param msg: The RTMP message to be sent by this stream.
        @type: L{message.Message}
        @param whenDone: An optional callback that is fired once the complete
            encoded RTMP message has been sent to the peer. This is not the same
            as a U{defer.Deferred} instance. When called it receives no params.
        """
        raise NotImplementedError


class NetStream(BaseStream):
    """
    A stream within an RTMP connection. A stream can either send or receive
    video/audio, or in the Flash vernacular - publish or subscribe.

    Not sure about data just yet.
    """

    def __init__(self, nc, streamId):
        BaseStream.__init__(self, streamId)

        self.nc = nc

    @property
    def client(self):
        return self.nc.client

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
        self.nc.sendMessage(msg, whenDone, stream=self)

    def deleteStream(self):
        """
        Called when this stream has been deleted from the NetConnection. Use it
        to clean up.
        """


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

        @param bytes: The number of bytes read when this interval was fired.
        """
        self.protocol.sendMessage(message.BytesRead(bytes))


class RTMPProtocol(protocol.Protocol, BaseStream):
    """
    Provides basic handshaking and RTMP protocol support.

    @ivar state: The state of the protocol. Can be either C{HANDSHAKE} or
        C{STREAM}.
    @type state: C{str}
    @ivar objectEncoding: The version to de/encode AMF packets. Set via the
        connect packet.
    """

    stream_class = NetStream

    HANDSHAKE = 'handshake'
    STREAM = 'stream'

    objectEncoding = pyamf.AMF0
    clientId = None

    def __init__(self):
        # this protocol is the NetConnection
        BaseStream.__init__(self, 0)

    def logAndDisconnect(self, reason, *args, **kwargs):
        """
        Called when something fatal has occurred. Logs any errors and closes the
        connection.
        """
        log.err(reason)
        self.transport.loseConnection()

        return reason

    def closeStream(self):
        pass

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
        def del_attr(attr):
            try:
                delattr(self, attr)
            except:
                pass

        if self.state == self.HANDSHAKE:
            del_attr('handshaker')
        elif self.state == self.STREAM:
            for streamId, stream in self.streams.copy().iteritems():
                if stream is self:
                    continue

                stream.closeStream()
                self.deleteStream(streamId)

            self.closeStream()

            del_attr('streams')

            del_attr('decoder_task')
            del_attr('decoder')

            del_attr('encoder_task')
            del_attr('encoder')

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
        Called to start asynchronously iterating the decoder.

        @return: A C{Deferred} which will kill the task once the decoding is
            done or on error will kill the connection.
        @todo: Think about what should happen to the decoder if the connection
            is lost. Right now the decoder will happily continue producing data
            for this protocol.
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
        @todo: See _startDecoding todo. The same applies here.
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
        self.decoder = codec.Decoder(DecodingDispatcher(self), self)
        self.encoder = codec.Encoder(self.transport)

        self.decoder_task = None
        self.encoder_task = None

        self.streams = {
            0: self
        }
        self._nextStreamId = 1

    # IStreamFactory
    def getStream(self, streamId):
        """
        Returns the L{NetStream} instance related to the C{streamId}.
        """
        s = self.streams.get(streamId, None)

        if s is None:
            # the peer needs to call 'createStream' to make new streams.
            raise KeyError('Unknown stream %r' % (streamId,))

        return s

    # INetConnection

    def sendMessage(self, msg, whenDone=None, stream=None):
        """
        Sends an RTMP message to the peer. Not part of a public api, use
        C{stream.sendMessage} instead.

        @param stream: The stream instance that is sending the message.
        @type stream: L{NetStream}
        @param msg: The message being sent to the peer.
        @type msg: L{message.Message}
        @param whenDone: A callback fired when the message has been written to
            the RTMP stream. See L{BaseStream.sendMessage}
        """
        try:
            e = self.encoder
        except AttributeError:
            return

        if stream is None:
            stream = self

        buf = BufferedByteStream()

        # this will probably need to be rethought as this could block for an
        # unacceptable amount of time. For most messages however it seems to be
        # fast enough and the penalty for setting up a new thread is too high.
        msg.encode(buf)

        e.send(buf.getvalue(), msg.RTMP_TYPE, stream.streamId,
            stream.timestamp, whenDone)

        if e.active and not self.encoder_task:
            self._startEncoding()

    def setFrameSize(self, size):
        self.sendMessage(message.FrameSize(size))
        self.encoder.setFrameSize(size)

    def getStreamingChannel(self, stream):
        """
        """
        self.setFrameSize(4096)

        channel = self.encoder.acquireChannel()

        if not channel:
            # todo: make this better
            raise RuntimeError('No streaming channel available')

        return codec.StreamingChannel(channel, stream.streamId, self.transport)

    @expose
    def createStream(self):
        """
        Creates a new L{NetStream} and associates it with this protocol.
        """
        streamId = self._nextStreamId
        self.streams[streamId] = self.stream_class(self, streamId)

        self._nextStreamId += 1

        return streamId

    @expose
    def deleteStream(self, streamId):
        """
        Deletes an existing L{NetStream} associated with this NetConnection.

        @todo: What about error handling or if the NetStream is still receiving
            or streaming data?
        """
        if streamId == 0:
            return # can't delete the NetConnection

        stream = self.streams.pop(streamId, None)

        if stream:
            stream.deleteStream()

    def onFrameSize(self, size, timestamp):
        """
        Called when the peer sets its RTMP frame size.

        @param size: The new size of any RTMP frames sent from the peer.
        @param timestamp: Time this message was received.
        """
        self.decoder.setFrameSize(size)

    def onDownstreamBandwidth(self, interval, timestamp):
        """
        Called when the peer sends its RTMP bytes interval.

        @param interval: The number of bytes that must be received from the
            peer before sending an acknowledgement
        """
        self.decoder.setBytesInterval(interval)

    def onUpstreamBandwidth(self, bandwidth, extra, timestamp):
        """
        """

    def onControlMessage(self, msg, timestamp):
        """
        """

    def onBytesRead(self, bytes, timestamp):
        """
        """
