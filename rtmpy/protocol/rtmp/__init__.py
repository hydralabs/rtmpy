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
from twisted.internet import protocol, task
from pyamf.util import BufferedByteStream

from rtmpy.protocol import handshake, version
from rtmpy.protocol.rtmp import message, codec


#: Maximum number of streams that can be active per RTMP stream
MAX_STREAMS = 0xffff


class Stream(object):
    timestamp = 0

    def __init__(self, protocol):
        self.protocol = protocol

    def onInvoke(self, *args):
        print 'invoke', args

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


class ControlStream(Stream):
    def onFrameSize(self, size, timestamp):
        self.protocol.setFrameSize(size)

    def onDownstreamBandwidth(self, *args):
        print 'dsbw', args

    def onUpstreamBandwidth(self, *args):
        print 'usbw', args

    def onControlMessage(self, *args):
        print 'cm', args

    def onBytesRead(self, *args):
        print 'bytes-read', args


class RTMPProtocol(protocol.Protocol):
    """
    Provides basic handshaking and RTMP protocol support.

    @ivar state: The state of the protocol. Can be either C{HANDSHAKE} or
        C{STREAM}.
    @type state: C{str}
    """

    HANDSHAKE = 'handshake'
    STREAM = 'stream'


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

        self.decoder = codec.Decoder(self, self)
        self.encoder = codec.Encoder(self)

        self.decoder_task = None
        self.encoder_task = None

    # IStreamFactory
    def getStream(self, streamId):
        s = self.streams.get(streamId, None)

        if s is None:
            if streamId == 0:
                s = self.factory.getControlStream(self, streamId)
            else:
                s = Stream(self)

            self.streams[streamId] = s

        return s

    def dispatchMessage(self, stream, datatype, timestamp, data):
        m = message.get_type_class(datatype)()

        m.decode(BufferedByteStream(data))

        m.dispatch(stream, timestamp)

    def sendMessage(self, stream, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. Not part of a public api, use
        C{stream.sendMessage} instead.
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
