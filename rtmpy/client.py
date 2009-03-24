# -*- test-case-name: rtmpy.tests.test_client -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP client implementation.

@since: 0.1.0
"""

from twisted.internet import reactor, protocol

from rtmpy import rtmp, util, versions
from rtmpy

class ClientProtocol(rtmp.BaseProtocol):
    """
    Client RTMP Protocol.
    """
    version = versions.Version('10,0,12,36')

    def connectionMade(self):
        """
        Called when a connection has been made to this protocol instance. Used
        to do general setup and protocol initialisation.
        """
        rtmp.BaseProtocol.connectionMade(self)

        # generate and send initial handshake
        self.writeHeader()
        self.transport.write(self.handshake.generate())

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

        if self.debug:
            from pyamf.util import hexdump

            rtmp._debug(self, 'received handshake :')
            rtmp._debug(self, hexdump(self.received_handshake))

        hs = buffer.read(rtmp.HANDSHAKE_LENGTH)

        print hexdump(hs[:7])
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
        rtmp.BaseProtocol.onHandshakeSuccess(self)

        # send invoke->connect here


class ClientFactory(protocol.ClientFactory):
    """
    RTMP client protocol factory.
    """

    protocol = ClientProtocol
