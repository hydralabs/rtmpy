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
from twisted.internet import protocol, task
from zope.interface import Interface, Attribute, implements
from pyamf.util import BufferedByteStream

from rtmpy import message
from rtmpy.protocol.rtmp import codec
from rtmpy.protocol import interfaces



class ProtocolVersionError(Exception):
    """
    Base error class for RTMP protocol version errors.
    """



class UnknownProtocolVersion(ProtocolVersionError):
    """
    Raised if an endpoint sends a protocol version that cannot be handled.
    """



class ProtocolTooHigh(ProtocolVersionError):
    """
    Raised if a protocol version is greater than can the requested version.
    """



class MessageDispatcher(object):
    """
    A proxy class that listens for events fired from the L{codec.Decoder}.

    @param streamer: The L{BaseStreamer} instance attached to the decoder.
    """

    implements(interfaces.IMessageDispatcher)


    def __init__(self, streamer):
        self.streamer = streamer


    def dispatchMessage(self, stream, datatype, timestamp, data):
        """
        Called when the RTMP decoder has read a complete RTMP message.

        @param stream: The L{Stream} to receive this message.
        @param datatype: The RTMP datatype for the message.
        @param timestamp: The absolute timestamp this message was received.
        @param data: The raw data for the message.
        """
        m = message.classByType(datatype)()

        m.decode(BufferedByteStream(data))
        m.dispatch(stream, timestamp)



    def bytesInterval(self, bytes):
        """
        Called when a specified number of bytes has been read from the stream.
        The RTMP protocol demands that we send an acknowledge message to the
        peer. If we don't do this, Flash will stop streaming video/audio.

        @param bytes: The number of bytes read when this interval was fired.
        """
        self.streamer.bytesInterval(bytes)



class BaseStreamer(object):
    """
    Provides all the base functionality for handling an RTMP input/output.

    @ivar decoder: RTMP Decoder that is fed data via L{dataReceived}
    """

    implements(message.IMessageListener)

    dispatcher = MessageDispatcher


    @property
    def decoding(self):
        """
        Whether this streamer is currently decoding RTMP message/s.

        If all the input buffer has been consumed, this will be C{False}.
        """
        return getattr(self, 'decoding_task', None) is not None


    @property
    def encoding(self):
        """
        Whether this streamer is currently encoding RTMP message/s.
        """
        return getattr(self, 'encoding_task', None) is not None


    def getWriter(self):
        """
        Returns a file like object that provides a I{write} method. This must be
        provided by subclasses.

        For example, for L{protocol.Protocol} instances this should return
        C{self.transport}.
        """
        raise NotImplementedError


    def buildStreamManager(self):
        """
        Returns an instance that provides L{interfaces.IStreamManager}. This
        must be provided by subclasses.
        """
        raise NotImplementedError


    def getDispatcher(self):
        """
        Returns an instance that will provide L{interfaces.IMessageDispatcher}
        """
        return self.dispatcher(self)


    def bytesInterval(self, bytes):
        """
        """
        self.sendMessage(message.BytesRead(bytes), self.controlStream)


    def startStreaming(self):
        """
        This must be called before any RTMP data is received.
        """
        self.streamManager = self.buildStreamManager()
        self.controlStream = self.streamManager.getControlStream()

        self._decodingBuffer = BufferedByteStream()
        self._encodingBuffer = BufferedByteStream()

        self.decoder = codec.Decoder(self.getDispatcher(), self.streamManager,
            stream=self._decodingBuffer)
        self.encoder = codec.Encoder(self.getWriter(),
            stream=self._encodingBuffer)

        self.decoder_task = None
        self.encoder_task = None


    def stopStreaming(self, reason=None):
        """
        """
        self.streamManager.closeAllStreams()

        self._decodingBuffer.truncate()
        self._encodingBuffer.truncate()

        del self._decodingBuffer
        del self._encodingBuffer

        del self.decoder_task, self.decoder
        del self.encoder_task, self.encoder


    def dataReceived(self, data):
        """
        Data has been received by the endpoint.
        """
        self.decoder.send(data)

        if not self.decoding:
            self.startDecoding()


    def startDecoding(self):
        """
        Called to start the decoding process.

        @return: A C{Deferred} which will kill the task once the decoding is
            done or on error.
        """
        def cullTask(result):
            self.decoder_task = None

            return result

        self.decoder_task = task.coiterate(self.decoder)

        self.decoder_task.addBoth(cullTask)

        return self.decoder_task


    def startEncoding(self):
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

        return self.encoder_task


    def sendMessage(self, msg, stream, whenDone=None):
        """
        Sends an RTMP message to the peer. Not part of a public api, use
        C{stream.sendMessage} instead.

        @param msg: The message being sent to the peer.
        @type msg: L{message.IMessage}
        @param stream: The stream instance that is sending the message.
        @type stream: L{NetStream}
        @param whenDone: A callback fired when the message has been written to
            the RTMP stream. See L{BaseStream.sendMessage}
        """
        buf = BufferedByteStream()
        e = self.encoder

        # this will probably need to be rethought as this could block for an
        # unacceptable amount of time. For most messages however it seems to be
        # fast enough and the penalty for setting up a new thread is too high.
        msg.encode(buf)

        e.send(buf.getvalue(), msg.__data_type__,
            stream.streamId, stream.timestamp, whenDone)

        if e.active and not self.encoder_task:
            self.startEncoding()


    def setFrameSize(self, size):
        self.sendMessage(message.FrameSize(size))
        self.encoder.setFrameSize(size)


    def getStreamingChannel(self, stream):
        """
        """
        channel = self.encoder.acquireChannel()

        if channel is None:
            # todo: make this better
            raise RuntimeError('No streaming channel available')

        return codec.StreamingChannel(channel, stream.streamId, self.getWriter())


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



class StateEngine(BaseStreamer):
    """
    There are three stages to the protocol negotiations before RTMP message
    streaming can begin.

    Stage 1 - Version negotiation::

    The first byte in any RTMP connection is the I{protocol version} byte. This
    allows endpoints to negotiate which version of the protocol to proceed with.

    Valid values appear to be::

    - C{0x03}: plain old RTMP this is the baseline protocol that all
        implementations should default to.
    - C{0x06}: Used to signify an RTMPE connection.

    There is another (C{0x08}) but not documented at this time because how/why
    it is used is unclear.

    L{versionSuccess} must be called to move on to stage 2.

    Stage 2 - Handshake negotiations::

    The next 1536 * 2 bytes is handshaking data. This part is delegated to a
    handshake negotiator, which is based on the protocol version.

    L{handshakeSuccess} must be called to move on to stage 3.

    Stage 3 - RTMP Message streaming::


    Some docstring here.

    @ivar state: The state of the protocol.
    """

    STATE_VERSION = 'version'
    STATE_HANDSHAKE = 'handshake'
    STATE_STREAM = 'stream'

    state = None
    protocolVersion = 3


    def connectionMade(self):
        """
        Called when this a connection has been made.
        """
        self.state = self.STATE_VERSION

        self.startVersioning()


    def connectionLost(self, reason):
        """
        Called when the connection has been lost.

        @param reason: The reason for the disconnection
        """
        if self.state == self.STATE_VERSION:
            self.stopVersioning(reason)
        elif self.state == self.STATE_HANDSHAKE:
            self.stopHandshaking(reason)
        elif self.state == self.STATE_STREAM:
            self.stopStreaming(reason)


    def dataReceived(self, data):
        """
        """
        if self.state == self.STATE_VERSION:
            self.version_dataReceived(data)
        elif self.state == self.STATE_HANDSHAKE:
            self.handshake_dataReceived(data)
        elif self.state == self.STATE_STREAM:
            BaseStreamer.dataReceived(self, data)
        else:
            raise RuntimeError('Invalid state!')


    def startVersioning(self):
        """
        Start protocol version negotiations.
        """
        self.buffer = BufferedByteStream()


    def stopVersioning(self, reason=None):
        """
        Stop protocol version negotiations.

        @param reason: A L{failure.Failure} object if protocol version
            negotiations failed. C{None} means success.
        """
        del self.buffer


    def version_dataReceived(self, data):
        """
        """
        if not data:
            return

        self.buffer.append(data)

        self.peerProtocolVersion = self.buffer.read_uchar()

        self.versionReceived(self.peerProtocolVersion)


    def versionReceived(self, version):
        """
        Called when the peers' protocol version has been received.

        The default behaviour is to accept any known version. It is the
        responsibility for any overriding subclass to call L{versionSuccess} for
        negotiations to proceed.
        """
        if version == self.protocolVersion:
            self.versionSuccess()

            return

        raise UnknownProtocolVersion(
            'Unhandled protocol version %d' % (version,))


    def versionSuccess(self):
        """
        Protocol version negotiations have been successful, now on to
        handshaking.
        """
        try:
            data = self.buffer.read()
        except IOError:
            data = None

        self.stopVersioning()

        self.state = self.STATE_HANDSHAKE

        self.startHandshaking()

        if data:
            # any data that was left over from version negotiations is
            # artificially re-inserted back into the protocol because the
            # `state` has changed.
            self.dataReceived(data)


    def buildHandshakeNegotiator(self):
        """
        """
        raise NotImplementedError


    def startHandshaking(self):
        """
        """
        self.handshaker = self.buildHandshakeNegotiator()

        # TODO: apply uptime, version to the handshaker instead of 0, 0
        self.handshaker.start(0, 0)


    def stopHandshaking(self, reason=None):
        """
        """
        del self.handshaker


    def handshake_dataReceived(self, data):
        """
        """
        self.handshaker.dataReceived(data)


    def handshakeSuccess(self, data):
        """
        Handshaking was successful, streaming now commences.
        """
        #data = self.handshaker.getRemainingData()

        self.stopHandshaking()

        self.state = self.STATE_STREAM

        self.startStreaming()

        if data:
            self.dataReceived(data)


    def startStreaming(self):
        """
        Because Python is awesome we can short circuit checking state each time
        L{dataReceived} is called.
        """
        self.dataReceived = lambda x: BaseStreamer.dataReceived(self, x)

        return BaseStreamer.startStreaming(self)



class ProtocolMessageDispatcher(MessageDispatcher):
    pass



class RTMPProtocol(StateEngine, protocol.Protocol):
    """
    """

    streamId = 0
    timestamp = 0


    def logAndDisconnect(self, reason, *args, **kwargs):
        """
        Called when something fatal has occurred. Logs any errors and closes the
        connection.
        """
        log.err(reason)
        self.transport.loseConnection()

        return reason


    def getWriter(self):
        """
        """
        return self.transport


    def buildHandshakeNegotiator(self):
        return self.factory.buildHandshakeNegotiator(self, self.transport)

    def dataReceived(self, data):
        try:
            StateEngine.dataReceived(self, data)
        except:
            self.logAndDisconnect(failure.Failure())


    def startDecoding(self):
        """
        """
        d = StateEngine.startDecoding(self)

        d.addErrback(self.logAndDisconnect)

        return d


    def startEncoding(self):
        """
        """
        d = StateEngine.startEncoding(self)

        d.addErrback(self.logAndDisconnect)

        return d
