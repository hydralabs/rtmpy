# Copyright The RTMPy Project
# See LICENSE for details

"""
RTMP implementation.

The Real Time Messaging Protocol (RTMP) is a protocol that is primarily used
to stream audio and video over the internet to the U{Adobe Flash Player<http://
en.wikipedia.org/wiki/Flash_Player>}.

The protocol is a container for data packets which may be
U{AMF<http://osflash.org/documentation/amf>} or raw audio/video data like
found in U{FLV<http://osflash.org/flv>}. A single connection is capable of
multiplexing many NetStreams using different channels. Within these channels
packets are split up into fixed size body chunks.

@see: U{RTMP (external)<http://rtmpy.org/wiki/RTMP>}
@since: 0.1
"""

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

    def logAndDisconnect(self, *args):
        from twisted.python import log

        log.err()
        self.transport.loseConnection()

    def connectionMade(self):
        """
        Called when this a connection has been made.
        """
        self.state = self.HANDSHAKE

        self.handshaker = self.factory.buildHandshakeNegotiator(self)

        self.handshaker.start(0, 0)

    def dataReceived(self, data):
        """
        Called when data is received from the underlying L{transport}.
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

    def handshakeSuccess(self, data):
        """
        Called when the RTMP handshake was successful. Once called, message
        streaming can commence.
        """
        from rtmpy.protocol.rtmp import codec

        self.state = self.STREAM

        del self.handshaker

        self.startStreaming()

        if data:
            self.dataReceived(data)

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

    def startStreaming(self):
        """
        Called to prep the protocol to accept and produce RTMP messages.
        """
        self.streams = {}
        self.application = None

        self.decoder = codec.Decoder(self, self)
        self.encoder = codec.Encoder(self)
        self._startDecoding()
        self._startEncoding()

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
