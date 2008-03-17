# -*- test-case-name: rtmpy.tests.test_client -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
Client implementation.

@author: U{Arnar Birgisson<mailto:arnarbi@gmail.com>}
@author: U{Thijs Triemstra<mailto:info@collab.nl>}
@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}

@since: 0.1.0
"""

from twisted.internet import reactor, protocol

from rtmpy import rtmp, util
import pyamf

class RTMPClientProtocol(rtmp.BaseProtocol):
    """
    Client RTMP Protocol.
    """

    def connectionMade(self):
        """
        Called when a connection has been made to this protocol instance. Used
        to do general setup and protocol initialisation.
        """
        rtmp.BaseProtocol.connectionMade(self)

        # generate and send initial handshake
        self.my_handshake = rtmp.generate_handshake()

        self.transport.write(rtmp.HEADER_BYTE + self.my_handshake)

    def _decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol.

        @see: U{RTMP handshake on OSFlash (external)
        <http://osflash.org/documentation/rtmp#handshake>} for more info.
        """
        if self.debug:
            rtmp._debug(self, "Begin decode handshake")
        buffer = self.buffer

        if len(buffer) < 1:
            # no data has been received yet
            if self.debug:
                rtmp._debug(self, "Header not received")
            return

        if self.received_handshake is None and buffer.read(1) != rtmp.HEADER_BYTE:
            self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Invalid header byte received')

            return

        self.received_handshake = ''

        if buffer.remaining() < rtmp.HANDSHAKE_LENGTH * 2:
            # buffer is too small, wait for more data
            return

        self.received_handshake = buffer.read(rtmp.HANDSHAKE_LENGTH)
        hs = buffer.read(rtmp.HANDSHAKE_LENGTH)

        if hs[8:] != self.my_handshake[8:]:
            self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Handshake mismatch')
        else:
            self.transport.write(self.received_handshake)
            self.dispatchEvent(rtmp.HANDSHAKE_SUCCESS)

    def decodeHandshake(self, data):
        self.buffer.seek(0, 2)
        self.buffer.write(data)
        self.buffer.seek(0)
        self._decodeHandshake()
        self.buffer.consume()

    def onHandshakeSuccess(self):
        """
        Successful handshake between client and server.
        """
        if self.debug:
            rtmp._debug(self, "handshake success")

        rtmp.BaseProtocol.onHandshakeSuccess(self)

        # send invoke->connect here

    def invoke(self, stream, *args, **kwargs):
        if stream is None:
            stream = self.stream_manager.getStream(0)

        data = pyamf.encode(args[0], 1, kwargs).getvalue()
        channel = self.channel_manager.createChannel()
        channel.body.write(data)
        channel.body.seek(0)
        channel.type = rtmp.ChannelTypes.INVOKE
        channel.stream_id = self.stream_manager.getStreamId(stream)
        channel.timer = 0
        channel.length = len(data)

        self.registerProducingChannel(channel)

class RTMPClientFactory(protocol.ClientFactory):
    """
    RTMP client protocol factory.
    """

    protocol = RTMPClientProtocol
