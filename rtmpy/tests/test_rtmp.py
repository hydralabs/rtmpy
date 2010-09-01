# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import protocol
from twisted.test.proto_helpers import StringTransportWithDisconnection

from rtmpy import protocol
from rtmpy.protocol import interfaces, codec, handshake

from rtmpy.tests.rtmp import mocks


class Pausable(object):
    """
    """

    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True


class DataReceiver(object):
    """
    """

    def __init__(self):
        self.buffer = []

    def dataReceived(self, data):
        self.buffer.append(data)


class BaseProtocolTestCase(unittest.TestCase):
    """
    Tests for L{protocol.BaseProtocol}
    """

    def _buildHandshakeNegotiator(self):
        self.handshakeNegotiator = object()

        return self.handshakeNegotiator

    def test_interface(self):
        self.assertTrue(
            interfaces.IHandshakeObserver.implementedBy(protocol.BaseProtocol))

        p = protocol.BaseProtocol()

        self.assertTrue(interfaces.IHandshakeObserver.providedBy(p))

    def test_create(self):
        p = protocol.BaseProtocol()

        self.assertEquals(p.debug, protocol.DEBUG)

    def test_buildHandshakeNegotiator(self):
        p = protocol.BaseProtocol()

        self.assertRaises(NotImplementedError, p.buildHandshakeNegotiator)

    def test_connectionMade(self):
        p = protocol.BaseProtocol()

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
        self.assertEquals(p.state, protocol.BaseProtocol.HANDSHAKE, 'handshake')

    def test_connectionLost(self):
        p = protocol.BaseProtocol()

        self.executed = False

        def connectionLost(protocol, reason):
            self.executed = True
            self.reason = reason

        cm = protocol.Protocol.connectionLost
        protocol.Protocol.connectionLost = connectionLost
        reason = object()

        p.encoder = Pausable()
        p.decoder = Pausable()

        try:
            p.connectionLost(reason)
        finally:
            protocol.Protocol.connectionLost = cm

        self.assertTrue(self.executed)
        self.assertIdentical(self.reason, reason)
        self.assertTrue(p.encoder.paused)
        self.assertTrue(p.decoder.paused)

    def test_decodeHandshake(self):
        p = protocol.BaseProtocol()

        p.buildHandshakeNegotiator = self._buildHandshakeNegotiator
        d = p.handshaker = DataReceiver()

        p.decodeHandshake('hello')

        self.assertEquals(d.buffer, ['hello'])

    def test_decodeStream(self):
        p = protocol.BaseProtocol()

        d = p.decoder = DataReceiver()

        p.decodeStream('foo')

        self.assertEquals(d.buffer, ['foo'])

    def test_logAndDisconnect(self):
        p = protocol.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        try:
            p.connectionMade()
        except NotImplementedError:
            pass

        p.logAndDisconnect()

        self.assertFalse(p.transport.connected)

    def test_dataReceived(self):
        p = protocol.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        buffer = []

        p.buildHandshakeNegotiator = self._buildHandshakeNegotiator
        p.connectionMade()

        def buf(type, data):
            buffer.append((type, data))

        p.decodeStream = lambda d: buf('stream', d)
        p.decodeHandshake = lambda d: buf('handshake', d)

        p.state = 'handshake'
        p.dataReceived('foo')
        self.assertEquals(buffer, [('handshake', 'foo')])

        p.state = 'stream'
        p.dataReceived('bar')
        self.assertEquals(buffer, [('handshake', 'foo'), ('stream', 'bar')])

        p.state = 'not-telling'
        e = self.assertRaises(RuntimeError, p.dataReceived, 'baz')
        self.assertEquals(str(e), "Unknown state 'not-telling'")
        self.assertEquals(buffer, [('handshake', 'foo'), ('stream', 'bar')])

        self.assertFalse(p.transport.connected)

    def test_handshakeSuccess(self):
        p = protocol.BaseProtocol()
        p.transport = StringTransportWithDisconnection()

        p.buildHandshakeNegotiator = self._buildHandshakeNegotiator
        p.connectionMade()

        self.assertEquals(p.decoder, None)
        self.assertEquals(p.encoder, None)
        self.assertEquals(p.state, 'handshake')

        p.handshaker = 'foo'

        p.handshakeSuccess()

        d = p.decoder
        self.assertTrue(isinstance(d, codec.Decoder))

        do = p.decoder.observer
        self.assertTrue(isinstance(do, protocol.ErrorLoggingCodecObserver))
        self.assertIdentical(do.protocol, p)
        self.assertIdentical(do.codec, d)

        e = p.encoder
        self.assertTrue(isinstance(e, codec.Encoder))
        self.assertIdentical(e.consumer, p.transport)

        do = e.observer
        self.assertTrue(isinstance(do, protocol.ErrorLoggingCodecObserver))
        self.assertIdentical(do.protocol, p)
        self.assertIdentical(do.codec, e)

        self.assertEquals(p.state, 'stream')

        self.assertFalse(hasattr(p, 'handshaker'))

    def test_handshakeFailure(self):
        p = protocol.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.buildHandshakeNegotiator = self._buildHandshakeNegotiator
        p.connectionMade()

        p.connected = True

        p.handshakeFailure(None)

        self.assertFalse(p.transport.connected)

    def test_write(self):
        p = protocol.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.write('foo')

        self.assertEquals(p.transport.io.getvalue(), 'foo')


class ClientProtocolTestCase(unittest.TestCase):
    """
    Tests for L{protocol.ClientProtocol}
    """

    def test_handshake_negotiator(self):
        p = protocol.ClientProtocol()
        n = p.buildHandshakeNegotiator()

        self.assertTrue(isinstance(n, handshake.ClientNegotiator))
        self.assertFalse(n.started)
        self.assertIdentical(n.observer, p)

    def test_connection(self):
        p = protocol.ClientProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.handshaker = handshake.ClientNegotiator(p)
        p.connectionMade()

        self.assertTrue(p.handshaker.started)


class ServerProtocolTestCase(unittest.TestCase):
    """
    Tests for L{protocol.ServerProtocol}
    """

    def test_handshake_negotiator(self):
        p = protocol.ServerProtocol()
        n = p.buildHandshakeNegotiator()

        self.assertTrue(isinstance(n, handshake.ServerNegotiator))
        self.assertFalse(n.started)
        self.assertIdentical(n.observer, p)

    def test_connection(self):
        p = protocol.ServerProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.handshaker = handshake.ServerNegotiator(p)
        p.connectionMade()

        self.assertTrue(p.handshaker.started)

    def test_handshake_overflow(self):
        class SimpleBuffer(object):
            def __init__(self):
                self.buffer = None

        p = protocol.ServerProtocol()

        p.handshaker = SimpleBuffer()
        p.handshaker.buffer = 'foo'
        self.executed = False

        def dataReceived(data):
            self.assertEquals(data, 'foo')
            self.executed = True

        p.dataReceived = dataReceived
        p.handshakeSuccess()

        self.assertTrue(self.executed)


class StreamManagerTestCase(unittest.TestCase):
    """
    Tests for L{interfaces.IStreamManager} implementation of
    L{codec.BaseCodec}.
    """

    def setUp(self):
        self.protocol = protocol.BaseProtocol()

        self.protocol.buildHandshakeNegotiator = self._buildHandshakeNegotiator

        self.protocol.connectionMade()
        self.protocol.handshakeSuccess()

    def _buildHandshakeNegotiator(self):
        self.handshakeNegotiator = object()

        return self.handshakeNegotiator

    def test_init(self):
        self.assertEquals(self.protocol.streams, {})

    def test_registerStream(self):
        e = self.assertRaises(ValueError, self.protocol.registerStream, -1, None)
        self.assertEquals(str(e), 'streamId is not in range (got:-1)')
        self.assertEquals(self.protocol.streams, {})

        e = self.assertRaises(ValueError, self.protocol.registerStream, 0x10000, None)
        self.assertEquals(str(e), 'streamId is not in range (got:65536)')
        self.assertEquals(self.protocol.streams, {})

        # test a successful registration
        s = mocks.Stream()

        self.protocol.registerStream(1, s)
        self.assertEquals(self.protocol.streams, {1: s})

        # show that we can add the same stream twice
        self.protocol.registerStream(2, s)

        self.assertEquals(self.protocol.streams, {1: s, 2: s})

    def test_removeStream(self):
        self.assertEquals(self.protocol.streams, {})

        e = self.assertRaises(IndexError, self.protocol.removeStream, 2)
        self.assertEquals(str(e), 'Unknown streamId 2')
        self.assertEquals(self.protocol.streams, {})

        s1, s2 = object(), object()

        self.protocol.streams = {3: s1, 56: s2}

        e = self.assertRaises(IndexError, self.protocol.removeStream, 2)
        self.assertEquals(str(e), 'Unknown streamId 2')
        self.assertEquals(self.protocol.streams, {3: s1, 56: s2})

        x = self.protocol.removeStream(3)
        self.assertEquals(self.protocol.streams, {56: s2})
        self.assertIdentical(x, s1)

        y = self.protocol.removeStream(56)
        self.assertEquals(self.protocol.streams, {})
        self.assertIdentical(y, s2)
