# Copyright The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.handshake}.
"""

from twisted.trial import unittest
from twisted.python import failure

from rtmpy.protocol import handshake
from rtmpy.util import BufferedByteStream


class HandshakeObserver(object):
    """
    Provides a link from the negotiator to the test case.
    """

    failure = None

    def __init__(self, test):
        self.buffer = BufferedByteStream()
        self.test = test

    def write(self, data):
        self.buffer.write(data)

    def handshakeFailure(self, *args):
        self.failure = failure.Failure()

    def raiseException(self):
        if not self.failure:
            return

        self.failure.raiseException()

    def handshakeSuccess(self):
        self.test.succeeded = True


class BaseTestCase(unittest.TestCase):
    """
    Sets up a negotiator and buffer (which will contain all the output from the
    negotiator).
    """

    negotiator_class = None
    uptime = 0
    version = 0

    def setUp(self):
        self.succeeded = False
        self.observer = HandshakeObserver(self)
        self.negotiator = self.negotiator_class(self.observer)
        self.buffer = self.observer.buffer

    def assertHandshakeFailure(self, cls):
        return self.assertRaises(cls, self.observer.raiseException)


class ClientNegotiatorTestCase(BaseTestCase):
    """
    Base class for testing L{handshake.ClientNegotiator}
    """

    negotiator_class = handshake.ClientNegotiator


class ClientProtocolVersionTestCase(ClientNegotiatorTestCase):
    """
    Test cases for protocol version handling.
    """

    def setUp(self):
        ClientNegotiatorTestCase.setUp(self)

        self.negotiator.start(self.uptime, self.version)

    def test_invalid(self):
        """
        RTMP version has to be less than \x20 (' ')
        """
        self.negotiator.dataReceived('\x20')

        e = self.assertHandshakeFailure(handshake.ProtocolVersionError)

        self.assertEqual(str(e), 'Invalid protocol version')
        self.assertFalse(self.succeeded)

    def test_too_high(self):
        self.assertTrue(6 > self.negotiator.protocolVersion)

        self.negotiator.dataReceived('\x06')

        e = self.assertHandshakeFailure(handshake.ProtocolTooHigh)

        self.assertEqual(str(e), 'Unexpected protocol version')
        self.assertFalse(self.succeeded)

    def test_degraded(self):
        """
        This negotiator is speaking 6 but is asked to talk 3.
        """
        self.negotiator.protocolVersion = 6

        self.negotiator.dataReceived('\x03')

        e = self.assertHandshakeFailure(handshake.ProtocolDegraded)

        self.assertEqual(str(e), 'Protocol version did not match (got 3, '
            'expected 6)')
        self.assertFalse(self.succeeded)


class ClientSynTestCase(ClientNegotiatorTestCase):
    """
    High level tests for client syn handshake testing
    """

    def test_not_started(self):
        self.assertFalse(self.negotiator.started)
        self.negotiator.dataReceived(' ')

        e = self.assertHandshakeFailure(handshake.HandshakeError)

        self.assertEqual(str(e), 'Data was received, but negotiator was not started')
        self.assertFalse(self.succeeded)

    def test_restart(self):
        self.negotiator.start(self.uptime, self.version)

        e = self.assertRaises(handshake.HandshakeError, self.negotiator.start,
            self.uptime, self.version)

        self.assertEqual(str(e), 'Handshake negotiator cannot be restarted')
        self.assertFalse(self.succeeded)

    def test_initiate(self):
        self.uptime = 1234
        self.version = 5678

        self.negotiator.start(self.uptime, self.version)

        self.assertEqual(self.negotiator.protocolVersion, 3)

        self.buffer.seek(0)

        # protocol version
        self.assertEqual(self.buffer.read_uchar(), 3)
        self.assertEqual(self.buffer.remaining(), 1536)

        self.assertEqual(self.buffer.read_ulong(), self.uptime)
        self.assertEqual(self.buffer.read_ulong(), self.version)


class ClientPeerSynTestCase(ClientNegotiatorTestCase):
    """
    Tests for when then client ack has been sent.
    """

    def setUp(self):
        ClientNegotiatorTestCase.setUp(self)

        self.negotiator.start(self.uptime, self.version)

        self.syn = self.negotiator.my_syn
        self.buffer.truncate()

        self.negotiator.dataReceived('\x03')

    def send_peer_syn(self):
        self.negotiator.dataReceived('\xff' * 1536)

    def test_flood(self):
        self.negotiator.dataReceived(' ' * (1536 * 2 + 1))

        e = self.assertHandshakeFailure(handshake.HandshakeError)

        self.assertEqual(str(e), 'Unexpected trailing data after peer syn/ack')
        self.assertFalse(self.succeeded)

    def test_peer_syn_only(self):
        self.send_peer_syn()

        # make sure the client is still waiting
        self.assertEqual(self.buffer.getvalue(), '')
        self.assertFalse(self.succeeded)

    def test_peer_ack_uptime_failure(self):
        self.assertEqual(self.uptime, 0)

        self.send_peer_syn()

        self.negotiator.dataReceived('\x00\x00\x00\x01') # the equivalent to 1
        self.negotiator.dataReceived('\xff' * (1536 - 4))

        e = self.assertHandshakeFailure(handshake.VerificationError)

        self.assertEqual(str(e), 'Received uptime is not the same')
        self.assertFalse(self.succeeded)

    def test_peer_ack_payload_failure(self):
        self.send_peer_syn()

        bad_payload = '\xff' * (1536 - 8)

        self.assertNotEqual(self.syn.payload, bad_payload)

        self.syn.encode(self.buffer)
        self.buffer.seek(0)

        self.negotiator.dataReceived(self.buffer.read(8))
        self.negotiator.dataReceived(bad_payload)

        e = self.assertHandshakeFailure(handshake.VerificationError)

        self.assertEqual(str(e), 'Received payload is not the same')
        self.assertFalse(self.succeeded)

    def test_ack(self):
        self.send_peer_syn()

        self.syn.encode(self.buffer)
        self.buffer.seek(0)

        peer_ack = self.buffer.getvalue()
        self.buffer.truncate()

        self.negotiator.dataReceived(peer_ack)

        ack = self.negotiator.my_ack

        # client sends server ack
        self.assertEqual(len(self.buffer), 1536)
        self.buffer.seek(0)

        self.assertEqual(self.buffer.read(4), '\xff' * 4)
        self.assertEqual(self.buffer.read_ulong(), ack.timestamp)

        self.assertEquals(self.buffer.read(), ack.payload)

        self.assertTrue(self.succeeded)


class ServerNegotiatorTestCase(BaseTestCase):
    """
    Base class for testing L{handshake.PeerNegotiator}
    """

    negotiator_class = handshake.ServerNegotiator

    def recieve_client_version(self, version):
        self.negotiator.dataReceived(version)

        self.syn = self.negotiator.my_syn

    def receive_client_syn(self):
        # uptime
        self.negotiator.dataReceived('\x00\x00\x00\x01')
        # version
        self.negotiator.dataReceived('\x01\x02\x03\x04')

        # payload
        self.negotiator.dataReceived('\xff' * (1536 - 8))


class ServerProtocolVersionTestCase(ServerNegotiatorTestCase):
    """
    Test cases for protocol version handling.
    """

    def setUp(self):
        ServerNegotiatorTestCase.setUp(self)

        self.negotiator.start(self.uptime, self.version)

    def test_invalid(self):
        """
        RTMP version has to be less than \x20 (' ')
        """
        self.recieve_client_version('\x20')

        e = self.assertHandshakeFailure(handshake.ProtocolVersionError)

        self.assertEqual(str(e), 'Invalid protocol version')
        self.assertFalse(self.succeeded)

    def test_too_high(self):
        self.assertTrue(6 > self.negotiator.protocolVersion)

        self.recieve_client_version('\x06')

        e = self.assertHandshakeFailure(handshake.ProtocolTooHigh)

        self.assertEqual(str(e), 'Unexpected protocol version')
        self.assertFalse(self.succeeded)


class ServerStartTestCase(ServerNegotiatorTestCase):
    """
    """

    def test_not_started(self):
        self.assertFalse(self.negotiator.started)
        self.negotiator.dataReceived(' ')

        e = self.assertHandshakeFailure(handshake.HandshakeError)

        self.assertEqual(str(e), 'Data was received, but negotiator was not started')
        self.assertFalse(self.succeeded)

    def test_restart(self):
        self.negotiator.start(self.uptime, self.version)

        e = self.assertRaises(handshake.HandshakeError, self.negotiator.start,
            self.uptime, self.version)

        self.assertEqual(str(e), 'Handshake negotiator cannot be restarted')
        self.assertFalse(self.succeeded)

    def test_initiate(self):
        self.uptime = 1234
        self.version = 5678

        self.negotiator.start(self.uptime, self.version)

        self.assertEqual(self.negotiator.protocolVersion, 3)
        self.recieve_client_version('\x03')

        self.buffer.seek(0)

        # protocol version
        self.assertEqual(self.buffer.read_uchar(), 3)
        self.assertEqual(self.buffer.remaining(), 1536)

        self.assertEqual(self.buffer.read_ulong(), self.uptime)
        self.assertEqual(self.buffer.read_ulong(), self.version)
        self.assertEqual(self.buffer.read(), self.syn.payload)


class ServerSynTestCase(ServerNegotiatorTestCase):
    """
    Tests for sending the server syn.
    """

    def setUp(self):
        ServerNegotiatorTestCase.setUp(self)

        self.negotiator.start(self.uptime, self.version)

        self.recieve_client_version('\x03')
        self.buffer.truncate()

    def test_receive_client_syn(self):
        self.assertEqual(self.buffer.getvalue(), '')

        self.receive_client_syn()

        self.assertEqual(len(self.buffer), 1536)

        self.buffer.seek(0)

        self.assertEqual(
            self.buffer.read_ulong(), self.negotiator.peer_syn.timestamp)
        self.assertEqual(
            self.buffer.read_ulong(), self.negotiator.my_ack.timestamp)

        self.assertEqual(self.buffer.read(), self.negotiator.my_ack.payload)
        self.assertFalse(self.succeeded)


class ServerClientAckTestCase(ServerNegotiatorTestCase):
    """
    Tests for client ack verification
    """

    def setUp(self):
        ServerNegotiatorTestCase.setUp(self)

        self.negotiator.start(self.uptime, self.version)

        self.recieve_client_version('\x03')
        self.buffer.truncate()

    def test_waiting(self):
        self.receive_client_syn()
        # make sure the client is still waiting
        self.assertFalse(self.succeeded)

    def test_peer_ack_uptime_failure(self):
        self.assertEqual(self.uptime, 0)

        self.receive_client_syn()
        self.buffer.truncate()

        self.negotiator.dataReceived('\x00\x00\x00\x01') # the equivalent to 1
        self.negotiator.dataReceived('\xff' * (1536 - 4))

        e = self.assertHandshakeFailure(handshake.VerificationError)

        self.assertEqual(str(e), 'Received uptime is not the same')
        self.assertFalse(self.succeeded)

    def test_peer_ack_payload_failure(self):
        self.receive_client_syn()
        self.buffer.truncate()

        self.buffer.write_ulong(self.syn.first)
        self.buffer.write('\xff' * (1536 - 4))

        bad_payload = self.buffer.getvalue()
        self.buffer.truncate()

        self.negotiator.dataReceived(bad_payload)

        e = self.assertHandshakeFailure(handshake.VerificationError)

        self.assertEqual(str(e), 'Received payload does not match')
        self.assertFalse(self.succeeded)

    def test_ack(self):
        self.receive_client_syn()
        self.buffer.truncate()

        self.syn.encode(self.buffer)
        payload = self.buffer.getvalue()
        self.buffer.truncate()

        self.negotiator.dataReceived(payload)
        self.assertTrue(self.succeeded)
