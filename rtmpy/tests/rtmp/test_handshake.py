# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.handshake}.
"""

from twisted.trial import unittest
from twisted.python import failure
from zope.interface import implements
from pyamf import EOStream

from rtmpy.rtmp import handshake, interfaces
from rtmpy import util, versions
from rtmpy.tests.rtmp import mocks


class BaseTokenTestCase(unittest.TestCase):
    """
    Base class for generating tokens
    """

    def _generatePayload(self, t, payload):
        t.__class__.generatePayload(t)

        p = t.payload.tell()
        t.payload.seek(2, 0)
        t.payload.write(payload)
        t.payload.seek(p)

    def _generateToken(self, *args, **kwargs):
        payload = None
        generate = kwargs.pop('generate', False)

        if generate:
            payload = kwargs.pop('payload', None)
        else:
            payload = kwargs.get('payload', None)

        t = self.token_class(*args, **kwargs)

        if generate and payload is not None:
            t.generatePayload = lambda: self._generatePayload(t, payload)

        return t


class TokenClassTestCase(BaseTokenTestCase):
    """
    Tests for L{handshake.Token}
    """

    token_class = handshake.Token

    def test_init(self):
        t = self._generateToken()

        self.assertEquals(t.uptime, 0)
        self.assertEquals(t.version, 0)
        self.assertEquals(t.payload, None)

        t = self._generateToken(payload='foo.bar')

        self.assertEquals(t.uptime, 0)
        self.assertEquals(t.version, 0)

        p = t.payload

        self.assertTrue(isinstance(p, util.BufferedByteStream))
        self.assertEquals(p.tell(), 0)
        self.assertEquals(p.getvalue(), 'foo.bar')

    def test_generate_payload(self):
        t = self.token_class()

        self.assertRaises(NotImplementedError, t.generatePayload)

    def test_encode(self):
        t = self._generateToken(payload='hi')

        self.assertEquals(t.encode(), 'hi')

    def test_str(self):
        t = self._generateToken(payload='hi', generate=True)

        self.assertRaises(NotImplementedError, str, t)

    def test_cmp(self):
        ta = self._generateToken(payload='hi')
        tb = self._generateToken(payload='as')

        self.failUnless(ta > tb)
        self.failUnless(tb < ta)
        self.failUnless(ta >= tb)
        self.failUnless(tb <= ta)
        self.failUnless(ta != tb)
        self.failUnless(tb == 'as')
        self.failUnless(tb == tb)

        self.failIf(ta < tb)
        self.failIf(tb > ta)
        self.failIf(ta <= tb)
        self.failIf(tb >= ta)
        self.failIf(ta == tb)
        self.failIf(tb != 'as')
        self.failIf(tb != tb)


class ClientTokenClassTestCase(TokenClassTestCase):
    """
    Tests for L{handshake.ClientToken}
    """

    token_class = handshake.ClientToken

    def test_generate_payload(self):
        t = self._generateToken()

        self.assertEquals(t.payload, None)
        t.generatePayload()

        p = t.payload

        self.assertTrue(isinstance(p, util.BufferedByteStream))
        self.assertEquals(p.tell(), 0)
        self.assertEquals(len(p), 1536)

        t.generatePayload()

        self.assertIdentical(p, t.payload)

    def test_getDigest(self):
        t = self._generateToken()

        self.assertEquals(t.payload, None)
        e = self.assertRaises(handshake.HandshakeError, t.getDigest)
        self.assertEquals(str(e),
            'No digest available for an empty handshake')

        t = self.token_class(version=versions.H264_MIN_FLASH)
        # magic offset = 4
        t.payload = util.BufferedByteStream('\x00' * 8 + \
            '\x01' * 4 + '\x02' * 4 + '\x00' * 32)

        self.assertEquals(t.getDigest(), '\x00' * 32)

        s = ''.join([chr(x) for x in xrange(1, 100)])
        # magic offset = 10
        t.payload = util.BufferedByteStream('\x00' * 8  + s)
        # HACK
        del t._digest

        self.assertEquals(t.getDigest(),
            ''.join([chr(x) for x in xrange(15, 47)]))

    def test_str(self):
        t = self._generateToken(payload='hi', generate=True)

        self.assertEquals(str(t), t.encode())


class ClientTokenEncodingTestCase(BaseTokenTestCase):
    """
    Tests for L{handshake.ClientToken.encode}
    """

    token_class = handshake.ClientToken

    def basicChecks(self, t, payload, check):
        self.assertTrue(isinstance(t.payload, util.BufferedByteStream))

        self.assertEquals(t.payload.getvalue(), payload)
        self.assertEquals(len(payload), 1536)
        self.assertTrue(payload[:8], check)

    def test_defaults(self):
        t = self._generateToken()

        self.assertEquals(t.payload, None)
        self.assertEquals(t.version, 0)
        self.assertEquals(t.uptime, 0)

        self.basicChecks(t, t.encode(), '\x00' * 8)

    def test_uptime(self):
        t = self._generateToken(uptime=20000)
        self.basicChecks(t, t.encode(), '\x00\x00N \x00\x00\x00\x00')

        t = self._generateToken(uptime=2000000)
        self.basicChecks(t, t.encode(), '\x00\x1e\x84\x80\x00\x00\x00\x00')

    def test_version(self):
        t = self._generateToken(version=10)
        self.basicChecks(t, t.encode(), '\x00\x00\x00\x00\x00\x00\x00\x0a')

        t = self._generateToken(version=0x09007300)
        self.basicChecks(t, t.encode(), '\x00\x00\x00\x00\t\x00s\x00')


class ServerTokenClassTestCase(TokenClassTestCase):
    """
    Tests for L{handshake.ClientToken}
    """

    token_class = handshake.ServerToken

    def _generateToken(self, *args, **kwargs):
        client = handshake.ClientToken()

        return TokenClassTestCase._generateToken(self, client, *args, **kwargs)

    def test_generate_payload(self):
        def r():
            raise RuntimeError

        t = self._generateToken()
        c = t.client

        self.assertEquals(c.payload, None)
        self.assertEquals(t.payload, None)
        e = self.assertRaises(handshake.HandshakeError, t.generatePayload)
        self.assertEquals(str(e), 'No digest available for an empty handshake')

        t = self._generateToken()
        c = t.client

        t.getDigest = r
        c.generatePayload()
        t.generatePayload()
        p = t.payload

        self.assertTrue(isinstance(p, util.BufferedByteStream))
        self.assertEquals(p.tell(), 0)
        self.assertEquals(len(p), 1536 + 1536)

        self.assertEquals(p.getvalue()[1536:], str(c))

        t.generatePayload()

        self.assertIdentical(p, t.payload)

    def test_h264_payload(self):
        t = self._generateToken(version=versions.H264_MIN_FMS)
        c = t.client
        c.version = versions.H264_MIN_FLASH

        c.payload = util.BufferedByteStream('\x00' * 8 + \
            '\x01\x01\x01\x01' + '\x03' * 4 + '\x02' * 32 + '\x00' * (1536 - 48))

        self.assertEquals(len(c.payload), 1536)

        t.generatePayload()

        self.assertNotEquals(c.getDigest(), None)
        self.assertNotEquals(t.getDigest(), None)

        p = t.payload.getvalue()

        self.assertEquals(len(p), 1536 * 2)

        self.assertEquals(p[:4], '\x00\x00\x00\x00')
        self.assertEquals(p[4:8], '\x03\x00\x01\x01')
        self.assertEquals(p[4:8], '\x03\x00\x01\x01')
        self.assertEquals(p[1536 - 64:1536],
            handshake._digest(t.getDigest(), c.payload.getvalue()))

    def test_str(self):
        t = self._generateToken(payload='hi', generate=True)
        t.client.generatePayload()
        self.assertEquals(str(t), t.encode())

    def test_h264_client_no_server(self):
        t = self._generateToken()
        c = t.client
        c.version = versions.H264_MIN_FLASH

        c.payload = util.BufferedByteStream('\x00' * 8 + \
            '\x01\x01\x01\x01' + '\x03' * 4 + '\x02' * 32 + '\x00' * (1536 - 48))

        self.assertEquals(len(c.payload), 1536)

        e = self.assertRaises(handshake.HandshakeError, t.generatePayload)
        self.assertEquals(str(e), 'Client not H.264 compatible')


class ServerTokenDigestTestCase(BaseTokenTestCase):
    """
    Tests for L{handshake.ClientToken}
    """

    token_class = handshake.ServerToken

    def _generateToken(self, *args, **kwargs):
        client = handshake.ClientToken()

        return BaseTokenTestCase._generateToken(self, client, *args, **kwargs)

    def test_no_payload(self):
        t = self._generateToken()

        self.assertEquals(t.payload, None)
        e = self.assertRaises(handshake.HandshakeError, t.getDigest)
        self.assertEquals(str(e),
            'No digest available for an empty handshake')

    def test_version(self):
        t = self._generateToken(version=0)
        c = t.client

        c.generatePayload()
        t.generatePayload()

        t.client = None
        self.assertEquals(t.getDigest(), None)

    def test_repeat(self):
        t = self._generateToken(version=versions.H264_MIN_FMS)
        c = t.client
        c.version = versions.H264_MIN_FLASH

        c.generatePayload()
        t.payload = util.BufferedByteStream('hi')

        self.assertFalse(hasattr(t, '_digest'))
        d = t.getDigest()
        self.assertTrue(hasattr(t, '_digest'))
        self.assertEquals(d, t._digest)

        t.payload = None
        self.assertEquals(d, t.getDigest())

    def test_client_version(self):
        t = self._generateToken(version=versions.H264_MIN_FMS)
        c = t.client

        c.generatePayload()
        t.generatePayload()

        self.assertEquals(c.getDigest(), None)
        self.assertEquals(t.getDigest(), None)

    def test_digest(self):
        t = self._generateToken(version=versions.H264_MIN_FMS)
        c = t.client
        c.version = versions.H264_MIN_FLASH

        c.payload = util.BufferedByteStream('\x00' * 8 + \
            '\x01\x01\x01\x01' + ('\x02' * 4) + '\x00' * 32)
        t.payload = util.BufferedByteStream('a')

        self.assertEquals(t.getDigest(), 'LSL\xa3\x16(I-\x07\x82\xaf\xd3#' \
            '\xfa\xf9j]\x16\xd3NE\x0fc]u(\x0e\x8c\x93\t\xa6G')


class ByteGeneratingTestCase(unittest.TestCase):
    """
    Tests for handshake.generateBytes
    """

    def test_generate(self):
        x = handshake.generateBytes(1)

        self.assertTrue(isinstance(x, str))
        self.assertEquals(len(x), 1)

        x = handshake.generateBytes(500)

        self.assertTrue(isinstance(x, str))
        self.assertEquals(len(x), 500)

    def test_types(self):
        x = handshake.generateBytes(3L)

        e = self.assertRaises(TypeError, handshake.generateBytes, '3')
        self.assertEquals(str(e), 
            "int expected for length (got:<type 'str'>)")

        e = self.assertRaises(TypeError, handshake.generateBytes, object())
        self.assertEquals(str(e), 
            "int expected for length (got:<type 'object'>)")


class HelperTestCase(unittest.TestCase):
    """
    Tests for L{handshake._digest}
    """

    def test_digest(self):
        self.assertEquals(handshake._digest('foo', 'bar'), '\xf92\x0b\xaf' \
            '\x02I\x16\x9es\x85\x0c\xd6\x15m\xed\x01\x06\xe2\xbbj\xd8\xca' \
            '\xb0\x1b{\xbb\xeb\xe6\xd1\x06S\x17')

    def test_getHeader(self):
        t = handshake.ClientToken()
        self.assertEquals(t.context, None)

        self.assertEquals(handshake.getHeader(t), '\x03')

        t.context = object()
        self.assertEquals(handshake.getHeader(t), '\x06')

        t = handshake.ServerToken(handshake.ClientToken())
        self.assertEquals(t.context, None)

        self.assertEquals(handshake.getHeader(t), '\x03')

        t.context = object()
        self.assertEquals(handshake.getHeader(t), '\x06')


class ClientHandshakeDecodingTestCase(unittest.TestCase):
    """
    Tests for L{handshake.decodeClientHandshake}.
    """

    def test_types(self):
        self.assertRaises(TypeError, handshake.decodeClientHandshake, 123)
        # more here

    def test_no_data(self):
        f = handshake.decodeClientHandshake

        self.assertRaises(EOStream, f, '')
        self.assertRaises(IOError, f, 'a' * 5)
        self.assertRaises(IOError, f, 'a' * 11)
        self.assertRaises(IOError, f, 'a' * (1536 - 1))

    def test_decode(self):
        d = '\x01\x02\x03\x04\x09\x08\x07\x06' + ('a' * (1536 - 8))

        t = handshake.decodeClientHandshake(d)

        self.assertEquals(t.__class__, handshake.ClientToken)
        v = t.version

        self.assertEquals(v.__class__, versions.Version)
        self.assertEquals(t.version, 0x09080706)
        self.assertEquals(t.uptime, 0x1020304)

        self.assertEquals(t.payload.getvalue(),
            '\x01\x02\x03\x04\x09\x08\x07\x06' + ('a' * (1536 - 8)))


class ServerHandshakeDecodingTestCase(unittest.TestCase):
    """
    Tests for L{handshake.decodeServerHandshake}.
    """

    def setUp(self):
        self.client = object()

    def test_types(self):
        self.assertRaises(TypeError, handshake.decodeServerHandshake,
            self.client, 123)

    def test_no_data(self):
        f = handshake.decodeServerHandshake

        self.assertRaises(EOStream, f, self.client, '')
        self.assertRaises(IOError, f, self.client, 'a' * 5)
        self.assertRaises(IOError, f, self.client, 'a' * 11)
        self.assertRaises(IOError, f, self.client, 'a' * (1536 - 1))

    def test_decode(self):
        d = '\x01\x02\x03\x04\x09\x08\x07\x06' + ('a' * (1536 - 8))

        t = handshake.decodeServerHandshake(self.client, d)

        self.assertEquals(t.__class__, handshake.ServerToken)
        self.assertIdentical(t.client, self.client)
        v = t.version

        self.assertEquals(v.__class__, versions.Version)
        self.assertEquals(t.version, 0x09080706)
        self.assertEquals(t.uptime, 0x1020304)

        self.assertEquals(t.payload.getvalue(),
            '\x01\x02\x03\x04\x09\x08\x07\x06' + ('a' * (1536 - 8)))


class BaseNegotiatorTestCase(unittest.TestCase):
    """
    Tests for L{handshake.BaseNegotiator}.
    """

    klass = handshake.BaseNegotiator

    def test_interface(self):
        interfaces.IHandshakeNegotiator.implementedBy(self.klass)

    def test_init(self):
        x = object()

        e = self.assertRaises(TypeError, self.klass, x)
        self.assertEquals(str(e),
            "IHandshakeObserver interface expected (got:<type 'object'>)")

        x = mocks.HandshakeObserver()
        self.assertTrue(interfaces.IHandshakeObserver.providedBy(x))
        n = self.klass(x)

        self.assertTrue(interfaces.IHandshakeNegotiator.providedBy(n))
        self.assertIdentical(n.observer, x)
        self.assertEquals(n.server, None)
        self.assertEquals(n.started, False)
        self.assertEquals(n.client, None)
        self.assertEquals(n.buffer, '')

    def test_data(self):
        x = mocks.HandshakeObserver()
        n = self.klass(x)

        self.assertRaises(NotImplementedError, n.dataReceived, '')


class ServerNegotiatorTestCase(BaseNegotiatorTestCase):
    """
    Tests for L{handshake.ServerNegotiator}
    """

    klass = handshake.ServerNegotiator

    def setUp(self):
        self.observer = mocks.HandshakeObserver()
        self.negotiator = self.klass(self.observer)

    def test_start_defaults(self):
        self.assertFalse(hasattr(self.negotiator, 'header'))
        self.assertFalse(hasattr(self.negotiator, 'received_header'))
        self.assertEquals(self.negotiator.server, None)
        self.assertEquals(self.negotiator.client, None)
        self.assertFalse(self.negotiator.started)

        self.negotiator.start()

        self.assertEquals(self.negotiator.server, None)
        self.assertEquals(self.negotiator.client, None)
        self.assertEquals(self.negotiator.uptime, None)
        self.assertEquals(self.negotiator.version, None)
        self.assertEquals(self.negotiator.header, None)
        self.assertEquals(self.negotiator.received_header, None)
        self.assertEquals(self.negotiator.buffer, '')
        self.assertTrue(self.negotiator.started)

    def test_start_args(self):
        self.assertFalse(hasattr(self.negotiator, 'header'))
        self.assertFalse(hasattr(self.negotiator, 'received_header'))
        self.assertEquals(self.negotiator.server, None)
        self.assertEquals(self.negotiator.client, None)
        self.assertFalse(self.negotiator.started)

        self.negotiator.start('foo', 'bar')

        self.assertEquals(self.negotiator.server, None)
        self.assertEquals(self.negotiator.client, None)
        self.assertEquals(self.negotiator.uptime, 'foo')
        self.assertEquals(self.negotiator.version, 'bar')
        self.assertEquals(self.negotiator.header, None)
        self.assertEquals(self.negotiator.received_header, None)
        self.assertEquals(self.negotiator.buffer, '')
        self.assertTrue(self.negotiator.started)

    def test_generateToken(self):
        e = self.assertRaises(
            handshake.HandshakeError, self.negotiator.generateToken)
        self.assertEquals(str(e), '`start` must be called before ' \
            'generating server token')

        # test negotiator.client = None
        self.negotiator = self.klass(self.observer)
        self.negotiator.start()

        self.assertTrue(self.negotiator.started)
        self.assertEquals(self.negotiator.client, None)

        e = self.assertRaises(
            handshake.HandshakeError, self.negotiator.generateToken)
        self.assertEquals(str(e), 'client token is required before ' \
            'generating server token')

        # now test correct token generation with defaults
        self.negotiator = self.klass(self.observer)
        self.negotiator.start()

        x = self.negotiator.client = object()

        self.assertEquals(self.negotiator.uptime, None)
        self.assertEquals(self.negotiator.version, None)
        self.assertEquals(self.negotiator.server, None)
        self.assertTrue(self.negotiator.started)

        self.negotiator.generateToken()

        s = self.negotiator.server

        self.assertEquals(s.__class__, handshake.ServerToken)
        self.assertIdentical(s.client, x)
        # h.264 compatible
        self.assertEquals(s.version, versions.H264_MIN_FMS)
        self.assertEquals(s.uptime, 0)
        self.assertEquals(s.payload, None)

        # test version < h264 (should be 0)
        self.negotiator = self.klass(self.observer)
        self.negotiator.start(version=0x020102)

        x = self.negotiator.client = object()

        self.assertTrue(self.negotiator.version < versions.H264_MIN_FMS)
        self.assertEquals(self.negotiator.uptime, None)
        self.assertEquals(self.negotiator.server, None)
        self.assertTrue(self.negotiator.started)

        self.negotiator.generateToken()

        s = self.negotiator.server

        self.assertEquals(s.__class__, handshake.ServerToken)
        self.assertIdentical(s.client, x)
        self.assertEquals(s.version, 0)
        self.assertEquals(s.uptime, 0)
        self.assertEquals(s.payload, None)

        # test uptime
        self.negotiator = self.klass(self.observer)
        self.negotiator.start(uptime=12345)

        x = self.negotiator.client = object()

        self.assertEquals(self.negotiator.uptime, 12345)
        self.assertEquals(self.negotiator.server, None)
        self.assertTrue(self.negotiator.started)

        self.negotiator.generateToken()

        s = self.negotiator.server

        self.assertEquals(s.__class__, handshake.ServerToken)
        self.assertIdentical(s.client, x)
        self.assertEquals(s.version, versions.H264_MIN_FMS)
        self.assertEquals(s.uptime, 12345)
        self.assertEquals(s.payload, None)

    def test_data(self):
        """
        Check to make sure that if an exception occurs when receiving data,
        it is propagated to the observer correctly.

        @see: L{interfaces.IHandshakeObserver.handshakeFailure}
        """
        class CustomError(Exception):
            pass

        def err(data):
            raise CustomError

        self.negotiator.start()
        self.negotiator._dataReceived = err

        self.assertRaises(CustomError, self.negotiator._dataReceived, '')
        self.negotiator.dataReceived('')

        self.assertFalse(self.observer.success)
        r = self.observer.reason

        self.assertTrue(isinstance(r, failure.Failure))
        self.assertEquals(r.type, CustomError)


class ServerHandshakeNegotiationTestCase(unittest.TestCase):
    """
    Actually checks the handshake negotiation from the server pov.
    """

    def setUp(self):
        self.observer = mocks.HandshakeObserver()
        self.negotiator = handshake.ServerNegotiator(self.observer)

        self.negotiator.start()

    def test_not_started(self):
        o = mocks.HandshakeObserver()
        n = handshake.ServerNegotiator(o)

        self.assertFalse(n.started)
        n.dataReceived('')

        self.assertFalse(o.success)

        try:
            r = o.reason.raiseException()
        except handshake.HandshakeError, e:
            self.assertEquals(str(e), 'Data received, but not started')
        except:
            self.fail('Unexpected error')

    def test_nothing(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('')

        self.assertEquals(o.success, None)
        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        self.assertEquals(n.client, None)
        self.assertEquals(n.server, None)
        self.assertEquals(o.buffer, [])

    def test_unknown_header(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('f')

        self.assertFalse(o.success)

        try:
            r = o.reason.raiseException()
        except handshake.HeaderError, e:
            self.assertEquals(str(e), "Unknown header byte 'f'")
        except:
            self.fail('Unexpected error')

    def test_just_header(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('\x03')

        self.assertEquals(o.success, None)
        self.assertEquals(n.received_header, '\x03')
        self.assertEquals(n.buffer, '')

        self.assertEquals(n.client, None)
        self.assertEquals(n.server, None)
        self.assertEquals(o.buffer, [])

    def test_header_plus_trailing(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('\x03' + 'a' * (handshake.HANDSHAKE_LENGTH - 1))

        self.assertEquals(o.success, None)
        self.assertEquals(n.received_header, '\x03')
        self.assertEquals(n.buffer, 'a' * (handshake.HANDSHAKE_LENGTH - 1))

        self.assertEquals(n.client, None)
        self.assertEquals(n.server, None)
        self.assertEquals(o.buffer, [])

    def test_large_client(self):
        """
        Client payload is too much
        """
        n = self.negotiator
        o = self.observer

        n.received_header = '\x03'

        self.assertEquals(n.buffer, '')

        n.dataReceived('a' * (handshake.HANDSHAKE_LENGTH + 1))

        self.assertFalse(o.success)

        try:
            r = o.reason.raiseException()
        except handshake.HandshakeError, e:
            self.assertEquals(str(e), 'Unexpected trailing data in client ' \
                'handshake')
        except:
            self.fail('Unexpected error')

    def test_client_buffer(self):
        n = self.negotiator
        o = self.observer

        n.received_header = '\x03'
        n.buffer = 'b' * 10

        n.dataReceived('a' * (handshake.HANDSHAKE_LENGTH - 11))

        self.assertEquals(n.buffer, 'b' * 10 + \
            'a' * (handshake.HANDSHAKE_LENGTH - 11))
        self.assertEquals(o.success, None)

        n.dataReceived('c')

        c = n.client

        self.assertNotEquals(c, None)

        self.assertEquals(len(o.buffer), 1)
        d = o.buffer[0]

        self.assertEquals(d[0], n.header, n.received_header)
        self.assertEquals(d[1:], n.server_payload)
        self.assertTrue(o.success)


class ClientNegotiatorTestCase(BaseNegotiatorTestCase):
    """
    Tests for L{handshake.ClientNegotiator}
    """

    klass = handshake.ClientNegotiator

    def setUp(self):
        self.observer = mocks.HandshakeObserver()
        self.negotiator = self.klass(self.observer)

    def test_start(self):
        n = self.negotiator
        o = self.observer

        self.assertFalse(hasattr(n, 'header'))
        self.assertFalse(hasattr(n, 'received_header'))
        self.assertEquals(n.server, None)
        self.assertEquals(n.client, None)
        self.assertFalse(n.started)

        self.negotiator.start()

        self.assertEquals(n.server, None)
        self.assertNotEquals(n.client, None)
        self.assertEquals(n.uptime, None)
        self.assertEquals(n.version, None)
        self.assertEquals(n.header, '\x03')
        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')
        self.assertTrue(n.started)

        self.assertEquals(len(o.buffer), 1)
        d = o.buffer[0]

        self.assertEquals(d[0], n.header)
        self.assertEquals(d[1:], n.client_payload)

    def test_start_args(self):
        n = self.negotiator
        o = self.observer

        self.assertFalse(hasattr(n, 'header'))
        self.assertFalse(hasattr(n, 'received_header'))
        self.assertEquals(n.server, None)
        self.assertEquals(n.client, None)
        self.assertFalse(n.started)

        self.negotiator.start(4321, 1234)

        self.assertEquals(n.server, None)
        self.assertNotEquals(n.client, None)
        self.assertEquals(n.uptime, 4321)
        self.assertEquals(n.version, 1234)
        self.assertEquals(n.header, '\x03')
        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')
        self.assertTrue(n.started)

        self.assertEquals(len(o.buffer), 1)
        d = o.buffer[0]

        self.assertEquals(d[0], n.header)
        self.assertEquals(d[1:], n.client_payload)

    def test_generateToken(self):
        e = self.assertRaises(
            handshake.HandshakeError, self.negotiator.generateToken)
        self.assertEquals(str(e), '`start` must be called before ' \
            'generating server token')

        # now test correct token generation with defaults
        self.negotiator = self.klass(self.observer)
        self.negotiator.started = True
        self.negotiator.uptime = self.negotiator.version = None

        self.negotiator.generateToken()

        c = self.negotiator.client

        self.assertEquals(c.__class__, handshake.ClientToken)
        # h.264 compatible
        self.assertEquals(c.version, versions.H264_MIN_FLASH)
        self.assertEquals(c.uptime, 0)
        self.assertEquals(c.payload, None)
        self.assertEquals(c.context, None)

        # test version < h264 (should be 0)
        self.negotiator = self.klass(self.observer)
        self.negotiator.started = True
        self.negotiator.uptime = None
        self.negotiator.version = 0x020102

        self.assertTrue(self.negotiator.version < versions.H264_MIN_FLASH)
        self.assertEquals(self.negotiator.client, None)

        self.negotiator.generateToken()

        c = self.negotiator.client

        self.assertEquals(c.__class__, handshake.ClientToken)
        self.assertEquals(c.version, 0)
        self.assertEquals(c.uptime, 0)
        self.assertEquals(c.payload, None)

        # test uptime
        self.negotiator = self.klass(self.observer)
        self.negotiator.started = True
        self.negotiator.uptime = 12345
        self.negotiator.version = None

        self.negotiator.generateToken()

        c = self.negotiator.client

        self.assertEquals(c.__class__, handshake.ClientToken)
        self.assertEquals(c.version, versions.H264_MIN_FLASH)
        self.assertEquals(c.uptime, 12345)
        self.assertEquals(c.payload, None)

    def test_data(self):
        """
        Check to make sure that if an exception occurs when receiving data,
        it is propagated to the observer correctly.

        @see: L{interfaces.IHandshakeObserver.handshakeFailure}
        """
        class CustomError(Exception):
            pass

        def err(data):
            raise CustomError

        self.negotiator.start()
        self.negotiator._dataReceived = err

        self.assertRaises(CustomError, self.negotiator._dataReceived, '')
        self.negotiator.dataReceived('')

        self.assertFalse(self.observer.success)
        r = self.observer.reason

        self.assertTrue(isinstance(r, failure.Failure))
        self.assertEquals(r.type, CustomError)


class ClientHandshakeNegotiationTestCase(unittest.TestCase):
    """
    Actually checks the handshake negotiation from the client pov.
    """

    def setUp(self):
        self.observer = mocks.HandshakeObserver()
        self.negotiator = handshake.ClientNegotiator(self.observer)

        self.negotiator.start()

        self.assertEquals(len(self.observer.buffer), 1)
        # we reset the buffere because there are other tests that handle
        # the data in there - see ClientNegotiatorTestCase.test_start_args
        self.observer.buffer = []

    def test_not_started(self):
        o = mocks.HandshakeObserver()
        n = handshake.ClientNegotiator(o)

        self.assertFalse(n.started)
        n.dataReceived('')

        self.assertFalse(o.success)

        try:
            r = o.reason.raiseException()
        except handshake.HandshakeError, e:
            self.assertEquals(str(e), 'Data received, but not started')
        except:
            self.fail('Unexpected error')

    def test_nothing(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('')

        self.assertEquals(o.success, None)
        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        self.assertNotEquals(n.client, None)
        self.assertEquals(n.server, None)
        self.assertEquals(o.buffer, [])

    def test_unknown_header(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('f')

        self.assertFalse(o.success)

        try:
            r = o.reason.raiseException()
        except handshake.HeaderError, e:
            self.assertEquals(str(e),
                "Unknown header byte 'f'")
        except:
            self.fail('Unexpected error')

    def test_just_header(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('\x03')

        self.assertEquals(o.success, None)
        self.assertEquals(n.received_header, '\x03')
        self.assertEquals(n.buffer, '')

        self.assertNotEquals(n.client, None)
        self.assertEquals(n.server, None)
        self.assertEquals(o.buffer, [])

    def test_header_plus_trailing(self):
        n = self.negotiator
        o = self.observer

        self.assertEquals(n.received_header, None)
        self.assertEquals(n.buffer, '')

        n.dataReceived('\x03' + 'a' * (handshake.HANDSHAKE_LENGTH - 1))

        self.assertEquals(o.success, None)
        self.assertEquals(n.received_header, '\x03')
        self.assertEquals(n.buffer, 'a' * (handshake.HANDSHAKE_LENGTH - 1))

        self.assertNotEquals(n.client, None)
        self.assertEquals(n.server, None)
        self.assertEquals(o.buffer, [])

    def test_server(self):
        """
        Send enough data to build a complete server token
        """
        n = self.negotiator
        o = self.observer

        n.received_header = '\x03'

        self.assertEquals(n.buffer, '')

        n.dataReceived('a' * (handshake.HANDSHAKE_LENGTH))

        self.assertEquals(o.success, None)
        self.assertNotEquals(n.client, None)
        self.assertNotEquals(n.server, None)
        self.assertEquals(n.buffer, '')
        self.assertEquals(o.buffer, [])

        n.dataReceived('b')

        self.assertEquals(o.success, None)
        self.assertNotEquals(n.client, None)
        self.assertNotEquals(n.server, None)
        self.assertEquals(n.buffer, 'b')
        self.assertEquals(o.buffer, [])

    def test_handshake(self):
        n = self.negotiator
        o = self.observer

        n.received_header = '\x03'
        n.server = handshake.ServerToken(n.client, version=versions.H264_MIN_FMS)

        self.assertEquals(n.buffer, '')

        n.dataReceived(n.client.encode())

        self.assertTrue(o.success)
        self.assertNotEquals(n.client, None)
        self.assertNotEquals(n.server, None)
        self.assertEquals(n.buffer, '')
        self.assertEquals(o.buffer, [])

    def test_bad_handshake(self):
        n = self.negotiator
        o = self.observer

        n.received_header = '\x03'
        n.server = handshake.ServerToken(n.client)

        d = 'a' * 1536

        self.assertNotEquals(d, n.client.encode())

        self.assertEquals(n.buffer, '')

        n.dataReceived(d)

        self.assertFalse(o.success)

        try:
            r = o.reason.raiseException()
        except handshake.HandshakeVerificationError, e:
            self.assertEquals(str(e), '')
        except:
            self.fail('Unexpected error')
