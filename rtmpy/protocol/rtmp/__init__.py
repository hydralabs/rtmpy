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
import pyamf
from pyamf.util import BufferedByteStream
from zope.interface import Interface, Attribute

from rtmpy import core
from rtmpy.core import message
from rtmpy.protocol.rtmp import codec


class IChannelMeta(Interface):
    """
    Contains meta data related to a channel.
    """

    channelId = Attribute("An C{int} representing the linked channel.")
    timestamp = Attribute("The relative time value for the associated message.")
    datatype = Attribute("The datatype for the corresponding channel.")
    bodyLength = Attribute("The length of the channel body.")
    streamId = Attribute("An C{int} representing the linked stream.")



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
        try:
            m = message.get_type_class(datatype)()

            m.decode(BufferedByteStream(data))
            m.dispatch(stream, timestamp)
        except:
            self.protocol.logAndDisconnect(failure.Failure())



    def bytesInterval(self, bytes):
        """
        Called when a specified number of bytes has been read from the stream.
        The RTMP protocol demands that we send an acknowledge message to the
        peer. If we don't do this, Flash will stop streaming video/audio.

        @param bytes: The number of bytes read when this interval was fired.
        """
        try:
            self.protocol.sendMessage(message.BytesRead(bytes))
        except:
            self.protocol.logAndDisconnect(failure.Failure())



class RTMPProtocol(protocol.Protocol, core.BaseStream):
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
    clientId = None


    def logAndDisconnect(self, reason, *args, **kwargs):
        """
        Called when something fatal has occurred. Logs any errors and closes the
        connection.
        """
        log.err(reason)
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
        def del_attr(attr):
            try:
                delattr(self, attr)
            except:
                pass

        if self.state == self.HANDSHAKE:
            del_attr('handshaker')
        elif self.state == self.STREAM:
            self._decodingBuffer.truncate()
            self._encodingBuffer.truncate()

            del_attr('_decodingBuffer')
            del_attr('_encodingBuffer')

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
        self._decodingBuffer = BufferedByteStream()
        self._encodingBuffer = BufferedByteStream()

        self.decoder = codec.Decoder(DecodingDispatcher(self), self,
            stream=self._decodingBuffer)
        self.encoder = codec.Encoder(self.transport, stream=self._encodingBuffer)

        self.decoder_task = None
        self.encoder_task = None

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

        e.send(buf.getvalue(), msg.type, stream.streamId,
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
