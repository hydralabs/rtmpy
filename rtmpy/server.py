# -*- test-case-name: rtmpy.tests.test_server -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

from twisted.internet import reactor, protocol

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

        if self.received_handshake is not None:
            if len(buffer) < rtmp.HANDSHAKE_LENGTH:
                # buffer is too small, wait for more data
                return
        else:
            if len(buffer) < rtmp.HANDSHAKE_LENGTH + 1:
                # buffer is too small, wait for more data
                return

        buffer.seek(0)

        if self.received_handshake is None and buffer.read(1) != rtmp.HEADER_BYTE:
            self.dispatch(rtmp.HANDSHAKE_FAILURE, 'Invalid header byte received')

            return

        if self.received_handshake is None:
            self.received_handshake = buffer.read(rtmp.HANDSHAKE_LENGTH)
            self.my_handshake = rtmp.generate_handshake()

            self.transport.write(rtmp.HEADER_BYTE)
            self.transport.write(self.my_handshake)
            self.transport.write(self.received_handshake)

            self._consumeBuffer()
        elif buffer.read(rtmp.HANDSHAKE_LENGTH) != self.my_handshake:
            self.dispatch(rtmp.HANDSHAKE_FAILURE, 'Handshake mismatch')
        else:
            self._consumeBuffer()
            self.dispatch(rtmp.HANDSHAKE_SUCCESS)

    def dataReceived(self, data):
        """
        Called when some data has been received from the underlying transport
        """
        # seek to the end of the stream
        self.buffer.seek(0, 2)
        self.buffer.write(data)

        if self.state == rtmp.RTMPBaseProtocol.HANDSHAKE:
            self.decodeHandshake()
        else:
            rtmp.RTMPBaseProtocol.dataReceived(data)


class RTMPServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory
    """

    protocol = RTMPServerProtocol
