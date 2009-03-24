# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.handshake}.
"""

from twisted.trial import unittest

from rtmpy.rtmp import handshake
from rtmpy import util, versions


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
            '\x01\x01\x01\x01' + '\x02' * 32 + '\x00' * (1536 - 44))

        t.generatePayload()

        self.assertNotEquals(c.getDigest(), None)
        self.assertNotEquals(t.getDigest(), None)

        p = t.payload.getvalue()

        self.assertEquals(len(p), 1536 * 2)

        self.assertEquals(p[:4], '\x00\x00\x00\x00')
        self.assertEquals(p[4:8], '\x03\x00\x01\x01')
        self.assertEquals(p[4:8], '\x03\x00\x01\x01')
        self.assertEquals(p[1536 - 64:1536], t.getDigest())
        print repr(p)

    def test_str(self):
        t = self._generateToken(payload='hi', generate=True)
        t.client.generatePayload()
        self.assertEquals(str(t), t.encode())


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

        self.assertEquals(t.getDigest(),
            '4c534ca31628492d0782afd323faf96a5d16d34e450f635d75280e8c9309a647')


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


class HandshakeClassTestCase(unittest.TestCase):
    """
    """

    def test_init(self):
        h = handshake.Handshake()

        self.assertEquals(h.__dict__, {
            'client': None,
            'server': None
        })

    def test_getClient(self):
        h = handshake.Handshake()
        self.assertEquals(h.client, None)
        c = h.getClient()

        self.assertIdentical(h.client, c)
        self.assertTrue(isinstance(c, handshake.ClientToken))
        self.assertEquals(c.uptime, 0)
        self.assertEquals(c.version, versions.H264_MIN_VERSION)

        h = handshake.Handshake()

        x = h.client = object()

        c = h.getClient()
        self.assertIdentical(h.client, c, x)

    def test_setClient(self):
        h = handshake.Handshake()
        self.assertEquals(h.client, None)

        