# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.client}
"""

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy import client, rtmp
from rtmpy.tests import util

class HandshakeTestCase(unittest.TestCase):
    def setUp(self):
        self.protocol = client.RTMPClientProtocol()

        self.transport = util.StringTransportWithDisconnection()
        self.transport.protocol = self.protocol

    def test_make_connection(self):
        self.protocol.makeConnection(self.transport)

        buffer = self.transport.value()
        self.assertEquals(buffer[0], rtmp.HEADER_BYTE)
        self.assertEquals(len(buffer), rtmp.HANDSHAKE_LENGTH + 1)

        self.assertEquals(buffer[1:], self.protocol.my_handshake)

    def test_send_bad_header(self):
        d = defer.Deferred()

        def fire_event(x):
            self.assertFalse(self.transport.connected)
            d.callback(None)

        self.protocol.makeConnection(self.transport)
        self.protocol.addEventListener(rtmp.HANDSHAKE_FAILURE, fire_event)
        self.protocol.dataReceived('f')

        return d

    def test_send_no_data(self):
        self.protocol.makeConnection(self.transport)
        self.protocol.decodeHandshake()

        self.assertTrue(self.transport.connected)

    def test_send_invalid_handshake(self):
        d = defer.Deferred()
        self.protocol.makeConnection(self.transport)

        client_handshake = self.transport.value()[1:]
        bad_client_handshake = ('\x01' * rtmp.HANDSHAKE_LENGTH)

        self.assertNotEquals(client_handshake, bad_client_handshake)

        def event_listener(reason):
            d.callback(None)

        self.protocol.addEventListener(rtmp.HANDSHAKE_FAILURE, event_listener)
        self.protocol.dataReceived(rtmp.HEADER_BYTE + ('\x00' * rtmp.HANDSHAKE_LENGTH) + bad_client_handshake)

        return d

    def test_send_valid_handshake(self):
        self.protocol.makeConnection(self.transport)

        client_token = self.transport.value()[1:]
        server_token = ('\x01' * rtmp.HANDSHAKE_LENGTH)
        self.transport.clear()

        self.protocol.dataReceived(rtmp.HEADER_BYTE + server_token + client_token)
        self.assertTrue(self.transport.connected)

        self.assertEquals(server_token, self.transport.value())
        self.assertTrue(self.transport.connected)
