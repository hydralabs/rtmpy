# Copyright the RTMPy project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.protocol.rtmp}
"""

from twisted.trial import unittest

from rtmpy.protocol import rtmp


class MockHandshakeNegotiator(object):
    """
    """

    def __init__(self, test, protocol):
        self.test = test
        self.procotol = protocol
        self.started = False

    def start(self, uptime, version):
        self.started = True


class MockFactory(object):
    """
    """

    def __init__(self, test, protocol):
        self.test = test
        self.protocol = protocol

    def buildHandshakeNegotiator(self, protocol):
        self.test.assertIdentical(protocol, self.protocol)

        return self.test.handshaker

class ProtocolTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.protocol = rtmp.RTMPProtocol()
        self.handshaker = MockHandshakeNegotiator(self, self.protocol)

    def connect(self):
        self.protocol.factory = MockFactory(self, self.protocol)
        self.protocol.connectionMade()


class StateTest(ProtocolTestCase):
    """
    Test protocol state between not connected/handshaking/streaming/disconnected
    """

    def test_not_connected(self):
        self.assertFalse(hasattr(self.protocol, 'state'))

    def test_connect(self):
        self.connect()

        self.assertEqual(self.protocol.state, 'handshake')
        self.assertTrue(self.handshaker.started)

        self.assertIdentical(self.protocol.handshaker, self.handshaker)

    def test_stream(self):
        self.connect()
        self.protocol.handshakeSuccess('')

        self.assertEqual(self.protocol.state, 'stream')
        self.assertFalse(hasattr(self.protocol, 'handshaker'))
        self.assertEqual(self.protocol.streams, {})
        self.assertEquals(self.protocol.application, None)

    def test_stream_task(self):
        self.connect()
        self.protocol.handshakeSuccess('')

        self.assertNotEqual(self.protocol.decoder_task, None)

        return self.protocol.decoder_task.whenDone()