# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import protocol
from twisted.test.proto_helpers import StringTransportWithDisconnection

from rtmpy import rtmp
from rtmpy.rtmp import interfaces, codec


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


class MockDeferred(object):
    """
    """

    def __init__(self):
        self.callbacks = []

    def addErrback(self, f):
        self.callbacks.append((None, f))

    def addCallback(self, f):
        self.callbacks.append((f, None))


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

    def test_connectionLost(self):
        p = rtmp.BaseProtocol()

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
        p = rtmp.BaseProtocol()

        p.buildHandshakeNegotiator = self._buildHandshakeNegotiator
        d = p.handshaker = DataReceiver()

        p.decodeHandshake('hello')

        self.assertEquals(d.buffer, ['hello'])

    def test_decodeStream(self):
        p = rtmp.BaseProtocol()

        d = p.decoder = DataReceiver()
        f = MockDeferred()

        d.start = lambda: f
        d.deferred = None

        p.decodeStream('foo')

        self.assertEquals(d.buffer, ['foo'])
        self.assertEquals(f.callbacks, [(None, p.logAndDisconnect)])

        # test that when the deferred is active that the state doesn't change
        d.deferred = f
        p.decodeStream('bar')
        self.assertEquals(d.buffer, ['foo', 'bar'])
        self.assertEquals(f.callbacks, [(None, p.logAndDisconnect)])

    def test_logAndDisconnect(self):
        p = rtmp.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.logAndDisconnect()

        self.assertFalse(p.transport.connected)

    def test_dataReceived(self):
        p = rtmp.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        buffer = []

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
        p = rtmp.BaseProtocol()
        p.transport = StringTransportWithDisconnection()

        self.assertEquals(p.decoder, None)
        self.assertEquals(p.encoder, None)
        self.assertFalse(hasattr(p, 'state'))

        p.handshakeSuccess()

        d = p.decoder
        self.assertTrue(isinstance(d, codec.Decoder))
        self.assertIdentical(d.observer, p)

        e = p.encoder
        self.assertTrue(isinstance(e, codec.Encoder))
        self.assertIdentical(e.consumer, p.transport)

        self.assertEquals(p.state, 'stream')

    def test_handshakeFailure(self):
        p = rtmp.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.connected = True

        p.handshakeFailure(None)

        self.assertFalse(p.transport.connected)

    def test_write(self):
        p = rtmp.BaseProtocol()
        p.transport = StringTransportWithDisconnection()
        p.transport.protocol = p

        p.write('foo')

        self.assertEquals(p.transport.io.getvalue(), 'foo')
