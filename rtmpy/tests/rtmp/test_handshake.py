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
        self.assertEquals(str(t), t.encode())

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

    def test_getDigest(self):
        t = self._generateToken()

        self.assertEquals(t.payload, None)
        e = self.assertRaises(handshake.HandshakeError, t.getDigest)
        self.assertEquals(str(e),
            'No digest available for an empty handshake')

        t = self.token_class(version=versions.H264_FLASH_MIN_VERSION)
        # magic offset = 4
        t.payload = util.BufferedByteStream('\x01\x01\x01\x01' + '\x00' * 32)

        self.assertEquals(t.getDigest(), '\x00' * 32)

        s = ''.join([chr(x) for x in xrange(1, 100)])
        # magic offset = 10
        t.payload = util.BufferedByteStream(s)

        self.assertEquals(t.getDigest(),
            ''.join([chr(x) for x in xrange(11, 43)]))


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

        t.getDigest = r
        c.generatePayload()

        self.assertEquals(c.version, 0)

        t.generatePayload()
        p = t.payload

        self.assertTrue(isinstance(p, util.BufferedByteStream))
        self.assertEquals(p.tell(), 0)
        self.assertEquals(len(p), 1528)

    def test_generate_digest_payload(self):
        self.executed = False

        t = self._generateToken()
        c = t.client

        def getDigest():
            r = self.token_class.getDigest(t)
            self.executed = True

            return r

        t.getDigest = getDigest
        c.version = versions.H264_MIN_VERSION

        self.assertEquals(c.payload, None)
        self.assertEquals(t.payload, None)

        c.generatePayload()
        t.generatePayload()
        p = t.payload

        self.assertTrue(isinstance(p, util.BufferedByteStream))
        self.assertEquals(p.tell(), 0)
        self.assertEquals(len(p), 1528)
        self.assertTrue(self.executed)

    def test_getDigest(self):
        t = self._generateToken()

        self.assertEquals(t.payload, None)
        self.assertFalse(hasattr(t, 'digest'))
        e = self.assertRaises(handshake.HandshakeError, t.getDigest)
        self.assertEquals(str(e),
            'No digest available for an empty handshake')

        t = self._generateToken()
        c = t.client

        c.version = version=versions.H264_MIN_VERSION
        c.payload = util.BufferedByteStream('\x01\x01\x01\x01' + '\x00' * 32)

        s = ''.join([chr(x) for x in xrange(1, 100)])
        # magic offset = 10
        t.payload = util.BufferedByteStream(s)

        d = '4f1ebeecf80261467d4ed2b1285e1a32c31d0ceddb21e448190aee038d99abd9'
        self.assertEquals(t.getDigest(), d)

        t = self._generateToken()
        c = t.client

        c.generatePayload()
        t.generatePayload()
        self.assertEquals(c.version, 0)

        self.assertEquals(t.getDigest(), None)


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

        