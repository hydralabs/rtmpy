# Copyright (c) The RTMPy Project.
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

from twisted.python import log
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

    #: This value is based on tcp dumps from FME <-> FMS 3.5
    bytesReadInterval = 1251810L

    def logAndDisconnect(self, result, *args, **kwargs):
        """
        Called when something fatal has occurred. Logs any errors and closes the
        connection.
        """
        log.err()
        self.transport.loseConnection()

        return result

    def connectionMade(self):
        """
        Called when this a connection has been made.
        """
        self.state = self.HANDSHAKE

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
                if self.decoder_task:
                    self.decoder_task.pause()

                del self.decoder_task

            if hasattr(self, 'decoder') and self.decoder:
                del self.decoder

            if hasattr(self, 'encoder_task'):
                if self.encoder_task:
                    self.encoder_task.pause()

                del self.encoder_task

            if hasattr(self, 'encoder') and self.encoder:
                del self.encoder

    def dataReceived(self, data):
        """
        Called when data is received from the underlying C{transport}.
        """
        dr = getattr(self, '_' + self.state + '_dataReceived', None)

        try:
            dr(data)
        except:
            self.logAndDisconnect()

    def _stream_dataReceived(self, data):
        self.decoder.send(data)

        if self.decoder_task is None:
            self._setupDecoder()

    def _handshake_dataReceived(self, data):
        self.handshaker.dataReceived(data)

    def _cullDecoderTask(self, *args):
        self.decoder_task = None

    def _cullEncoderTask(self, *args):
        self.encoder_task = None

    def _startDecoding(self):
        """
        """
        self.decoder_task = task.cooperate(self.decoder)

        d = self.decoder_task.whenDone()

        d.addCallback(self._cullDecoderTask)
        d.addErrback(self.logAndDisconnect)

        return d

    def _startEncoding(self):
        self.encoder_task = task.cooperate(self.encoder)

        d = self.encoder_task.whenDone()

        d.addCallback(self._cullEncoderTask)
        d.addErrback(self.logAndDisconnect)

    def handshakeSuccess(self, data):
        """
        Handshaking was successful, streaming now commences.

        @param data: Any data left over from the handshake negotiations.
        """
        self.state = self.STREAM

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

        self._startDecoding()

    # IStreamFactory
    def getStream(self, streamId):
        s = self.streams.get(streamId, None)

        if s is None:
            if streamId == 0:
                s = ControlStream(self)
            else:
                s = Stream(self)

            self.streams[streamId] = s

        return s

    def dispatchMessage(self, stream, datatype, timestamp, data):
        m = message.get_type_class(datatype)()

        m.decode(BufferedByteStream(data))

        m.dispatch(stream, timestamp)
