# -*- test-case-name: rtmpy.tests.test_codec -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake support.
"""

import random, hmac, hashlib

from rtmpy import versions, util

SECRET_SERVER_KEY = \
    '\x47\x65\x6e\x75\x69\x6e\x65\x20\x41\x64\x6f\x62\x65\x20\x46\x6c\x61' \
    '\x73\x68\x20\x4d\x65\x64\x69\x61\x20\x53\x65\x72\x76\x65\x72\x20\x30' \
    '\x30\x31\xf0\xee\xc2\x4a\x80\x68\xbe\xe8\x2e\x00\xd0\xd1\x02\x9e\x7e' \
    '\x57\x6e\xec\x5d\x2d\x29\x80\x6f\xab\x93\xb8\xe6\x36\xcf\xeb\x31\xae'

HANDSHAKE_LENGTH = 1536
SHA256_DIGEST_LENGTH = 64


class HandshakeError(Exception):
    """
    Generic class for handshaking related errors.
    """


class Token(object):
    """
    Base functionality for handshake tokens.
    """

    def __init__(self, uptime=0, version=0, payload=None):
        self.uptime = uptime
        self.version = version

        self.payload = None

        if payload is not None:
            self.payload = util.BufferedByteStream(payload)

    def encode(self):
        """
        Called to encode the token to a byte string.
        """
        if self.payload is None:
            self.generatePayload()

        s = util.BufferedByteStream()

        s.write_ulong(self.uptime)
        s.write_ulong(int(self.version))
        s.write(self.payload.getvalue())

        return s.getvalue()

    def generatePayload(self):
        """
        """
        raise NotImplementedError

    def __str__(self):
        if hasattr(self, '_bytes'):
            return self._bytes

        self._bytes = self.encode()

        return self._bytes

    def __cmp__(self, other):
        return cmp(str(self), str(other))


class ClientToken(Token):
    """
    Represents a decoded client handshake.
    """

    def generatePayload(self):
        self.payload = util.BufferedByteStream(
            generateBytes(HANDSHAKE_LENGTH - 8))

    def getDigest(self):
        """
        """
        if self.payload is None:
            raise HandshakeError('No digest available for an empty handshake')

        if self.version < versions.H264_MIN_VERSION:
            return None

        b = self.payload
        pos = b.tell()
        b.seek(0)

        s = sum([b.read_uchar() for x in xrange(0, 4)])
        b.seek(s % 728)

        digest = b.read(32)
        b.seek(pos)

        return digest


class ServerToken(Token):
    """
    Represents a decoded server handshake.
    """

    def __init__(self, client, uptime=0, version=0, payload=None):
        Token.__init__(self, uptime, version, payload)

        self.client = client

    def generatePayload(self):
        if self.client.getDigest() is None:
            self.payload = util.BufferedByteStream(
                generateBytes(HANDSHAKE_LENGTH - 8))

            return

        self.payload = util.BufferedByteStream(
            generateBytes(HANDSHAKE_LENGTH - 8 - SHA256_DIGEST_LENGTH))

        self.payload.seek(0, 2)
        self.payload.write(self.getDigest())
        self.payload.seek(0)

    def getDigest(self):
        """
        """
        if self.payload is None:
            raise HandshakeError('No digest available for an empty handshake')

        client_digest = self.client.getDigest()

        if client_digest is None:
            return None

        return _digest(client_digest, self.payload.getvalue())


class Handshake(object):
    """
    Represents a handshake in all of its three phases.

    @see: L{http://rtmpy.org/wiki/RTMP#a3.Handshake} for more info
    """

    def __init__(self):
        self.server = None
        self.client = None

    def getClient(self):
        """
        Returns the client handshake. Will generate one if none exists.
        """
        if self.client is None:
            self.client = generateClient()

        return self.client

    def setClient(self, data):
        """
        Set the client handshake.
        """
        if isinstance(data, ClientToken):
            self.client = data

            return

        self.client = decodeClientHandshake(data)

    def getServer(self):
        """
        Returns the server handshake. Will generate one if none exists.
        """
        if self.server is not None:
            return self.server

        self.server = generateServer(self.getClient())

    def setServer(self, data):
        """
        Set the server handshake.
        """
        if isinstance(data, ServerToken):
            self.server = data

            return

        if self.client is None:
            raise 

        self.server = decodeServerHandshake(self.getClient(), data)


def generateClient(uptime=None, version=None):
    """
    Generate a client handshake. The version is important if you want to
    enable H.264 support (the default).

    @param uptime: System uptime in milliseconds. If not supplied, then
        this will be figured out automagically.
    @type uptime: C{int} or C{None}
    @param version: The 4 part version of the client.
    @type version: L{Version} or C{int}
    """
    if uptime is None:
        uptime = util.uptime()

    if version is None:
        version = versions.H264_MIN_VERSION

    if version < versions.H264_MIN_VERSION:
        version = 0

    return ClientToken(uptime, version)


def decodeClientHandshake(data):
    """
    """
    s = util.BufferedByteStream(data)

    uptime = s.read_ulong()
    version = versions.Version(s.read_ulong())

    payload = s.read(HANDSHAKE_LENGTH - 8)

    return ClientToken(uptime, version, payload)


def decodeServerHandshake(client, data):
    """
    """
    s = util.BufferedByteStream(data)

    uptime = s.read_ulong()
    version = versions.Version(s.read_ulong())

    if client.version < versions.H264_MIN_VERSION:
        pass
        # we look for a digest


def generateBytes(length):
    """
    Generates a string of C{length} bytes of pseudo-random data. Used for 
    filling in the gaps in unknown sections of the handshake.
    """
    # FIXME: sloooow
    if type(length) not in [int, long]:
        raise TypeError('int expected for length (got:%s)' % (type(length),))

    bytes = ''

    for x in xrange(0, length):
        bytes += chr(random.randint(0, 0xff))

    return bytes


def _digest(key, payload):
    return hmac.new(key, msg=payload, digestmod=hashlib.sha256).hexdigest()
