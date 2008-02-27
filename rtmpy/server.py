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

    def _decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol.

        @see L{http://osflash.org/documentation/rtmp#handshake} for more info.
        """
        buffer = self.buffer

        if self.my_handshake is not None:
            # we have received the correct header, the peer's handshake,
            # sent our own handshake, time to validate.
            if buffer.remaining() < rtmp.HANDSHAKE_LENGTH:
                return

            hs = buffer.read(rtmp.HANDSHAKE_LENGTH)

            if hs[8:] != self.my_handshake[8:]:
                self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Handshake mismatch')

                return

            self.dispatchEvent(rtmp.HANDSHAKE_SUCCESS)

            return

        # check there is enough data to proceed ..
        if self.received_handshake is not None:
            if len(buffer) < rtmp.HANDSHAKE_LENGTH:
                return
        else:
            if len(buffer) < 1:
                return

        buffer.seek(0)

        if self.received_handshake is None and buffer.read(1) != rtmp.HEADER_BYTE:
            self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Invalid header byte received')

            return

        self.received_handshake = ''

        if buffer.remaining() < rtmp.HANDSHAKE_LENGTH:
            return

        self.received_handshake = buffer.read(rtmp.HANDSHAKE_LENGTH)
        self.my_handshake = rtmp.generate_handshake()

        self.transport.write(
            rtmp.HEADER_BYTE + self.my_handshake + self.received_handshake)

    def decodeHandshake(self):
        self._decodeHandshake()
        self.buffer.consume()

    def onHandshakeSuccess(self):
        rtmp.RTMPBaseProtocol.onHandshakeSuccess(self)

        if len(self.buffer) > 0:
            bytes = self.buffer.getvalue()
            self.buffer.truncate()

            self._callLater(0, self.dataReceived, bytes)


class RTMPServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory
    """

    protocol = RTMPServerProtocol
