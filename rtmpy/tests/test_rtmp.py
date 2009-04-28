# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import protocol

from rtmpy import rtmp
from rtmpy.rtmp import interfaces


class BaseProtocolTestCase(unittest.TestCase):
    """
    Tests for L{rtmp.BaseProtocol}
    """

    def _buildHandshakeNegotiator(self):
        self.handshakeNegotiator = object()

        return self.handshakeNegotiator

    def test_interface(self):
        self.assertTrue(
            interfaces.IHandshakeObserver.implementedBy(rtmp.BaseProtocol))
        self.assertTrue(
            interfaces.ICodecObserver.implementedBy(rtmp.BaseProtocol))

        p = rtmp.BaseProtocol()

        self.assertTrue(interfaces.IHandshakeObserver.providedBy(p))
        self.assertTrue(interfaces.ICodecObserver.providedBy(p))

    def test_create(self):
        p = rtmp.BaseProtocol()

        self.assertFalse(p.encrypted)
        self.assertEquals(p.debug, rtmp.DEBUG)
        self.assertEquals(p.decoder, None)
        self.assertEquals(p.encoder, None)

    def test_buildHandshakeNegotiator(self):
        p = rtmp.BaseProtocol()

        self.assertRaises(NotImplementedError, p.buildHandshakeNegotiator)

    def test_connectionMade(self):
        p = rtmp.BaseProtocol()

        p.buildHandshakeNegotiator = self._buildHandshakeNegotiator
        self.executed = False

        def connectionMade(protocol):
            self.executed = True

        cm = protocol.Protocol.connectionMade
        protocol.Protocol.connectionMade = connectionMade

        try:
            p.connectionMade()
        finally:
            protocol.Protocol.connectionMade = cm

        self.assertTrue(self.executed)
        self.assertEquals(self.handshakeNegotiator, p.handshaker)
        self.assertEquals(p.state, rtmp.BaseProtocol.HANDSHAKE, 'handshake')