# -*- test-case-name: rtmpy.tests.test_server -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

from twisted.internet import reactor, protocol
from twisted.python import log

from rtmpy import rtmp, util


class RTMPServerProtocol(rtmp.RTMPBaseProtocol):
    """
    Server RTMP Protocol.
    """

    def decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol.

        @see L{http://osflash.org/documentation/rtmp#handshake} for more info.
        """
        buffer = self.buffer

        # check there is enough data to proceed ..
        if self.received_handshake is not None:
            if len(buffer) < rtmp.HANDSHAKE_LENGTH:
                return
        else:
            if len(buffer) < rtmp.HANDSHAKE_LENGTH + 1:
                return

        buffer.seek(0)

        if self.received_handshake is None and buffer.read(1) != rtmp.HEADER_BYTE:
            self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Invalid header byte received')

            return

        if self.received_handshake is None:
            self.received_handshake = buffer.read(rtmp.HANDSHAKE_LENGTH)
            self.my_handshake = rtmp.generate_handshake()

            self.transport.write(
                rtmp.HEADER_BYTE + self.my_handshake + self.received_handshake)
            self._consumeBuffer()
        elif buffer.read(rtmp.HANDSHAKE_LENGTH) != self.my_handshake:
            self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Handshake mismatch')
        else:
            self._consumeBuffer()
            self.dispatchEvent(rtmp.HANDSHAKE_SUCCESS)

    def dataReceived(self, data):
        """
        Called when some data has been received from the underlying transport
        """
        rtmp.RTMPBaseProtocol.dataReceived(self, data)

        if self.state == rtmp.RTMPBaseProtocol.HANDSHAKE:
            self.decodeHandshake()

    def onHandshakeSuccess(self):
        rtmp.RTMPBaseProtocol.onHandshakeSuccess(self)

        if self.buffer.remaining() > 0:
            bytes = self.buffer.read()
            self.buffer.truncate()

            self._callLater(0, self.dataReceived, bytes)


class RTMPServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory
    """

    protocol = RTMPServerProtocol
