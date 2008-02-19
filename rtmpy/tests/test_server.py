# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.server}
"""

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy import server, rtmp
from rtmpy.tests import util

class HandshakeTestCase(unittest.TestCase):
    """
    Tests the handshaking phase of the server protocol
    """
    def setUp(self):
        self.protocol = server.RTMPServerProtocol()

        self.transport = util.StringTransportWithDisconnection()
        self.transport.protocol = self.protocol

    def test_receive_bad_header(self):
        d = defer.Deferred()
        self.protocol.makeConnection(self.transport)

        def onEvent(reason):
            self.assertFalse(self.transport.connected)

        self.protocol.addEventListener(rtmp.HANDSHAKE_FAILURE, onEvent)
        self.protocol.dataReceived('\x00' * (rtmp.HANDSHAKE_LENGTH + 1))

    def test_receive_no_data(self):
        self.protocol.makeConnection(self.transport)
        self.protocol.decodeHandshake()

        self.assertTrue(self.transport.connected)

    def test_receive_invalid_handshake(self):
        d = defer.Deferred()
        self.protocol.makeConnection(self.transport)

        self.protocol.dataReceived(rtmp.HEADER_BYTE + ('\x00' * rtmp.HANDSHAKE_LENGTH))

        client_handshake = self.protocol.received_handshake
        bad_client_handshake = '\x01' * rtmp.HANDSHAKE_LENGTH

        self.assertNotEquals(client_handshake, bad_client_handshake)

        def event_listener(reason):
            d.callback(None)

        self.protocol.addEventListener(rtmp.HANDSHAKE_FAILURE, event_listener)
        self.protocol.dataReceived(bad_client_handshake)

        return d

    def test_receive_valid_handshake(self):
        d = defer.Deferred()
        self.protocol.makeConnection(self.transport)

        client_hs = rtmp.generate_handshake()
        self.protocol.dataReceived(rtmp.HEADER_BYTE + client_hs)
        handshake = self.transport.value()

        self.assertEquals(handshake[0], rtmp.HEADER_BYTE)
        self.assertEquals(handshake[1:rtmp.HANDSHAKE_LENGTH + 1], self.protocol.my_handshake)
        self.assertEquals(handshake[1 + rtmp.HANDSHAKE_LENGTH:], client_hs)

        self.protocol.dataReceived(self.protocol.my_handshake)

        def onEvent():
            d.callback(None)

        self.protocol.addEventListener(rtmp.HANDSHAKE_SUCCESS, onEvent)

        return d
