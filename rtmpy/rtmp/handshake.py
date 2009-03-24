# -*- test-case-name: rtmpy.tests.rtmp.test_handshake -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake support.

@see: L{http://rtmpy.org/wiki/RTMP#a3.Handshake}
"""

import random, hmac, hashlib
from zope.interface import Interface, implements, Attribute
from twisted.python.failure import Failure

from rtmpy import versions, util

SECRET_SERVER_KEY = \
    '\x47\x65\x6e\x75\x69\x6e\x65\x20\x41\x64\x6f\x62\x65\x20\x46\x6c\x61' \
    '\x73\x68\x20\x4d\x65\x64\x69\x61\x20\x53\x65\x72\x76\x65\x72\x20\x30' \
    '\x30\x31\xf0\xee\xc2\x4a\x80\x68\xbe\xe8\x2e\x00\xd0\xd1\x02\x9e\x7e' \
    '\x57\x6e\xec\x5d\x2d\x29\x80\x6f\xab\x93\xb8\xe6\x36\xcf\xeb\x31\xae'

HANDSHAKE_LENGTH = 1536
SHA256_DIGEST_LENGTH = 64

RTMP_HEADER_BYTE = '\x03'
RTMPE_HEADER_BYTE = '\x06'


class HandshakeError(Exception):
    """
    Generic class for handshaking related errors.
    """


class HeaderMismatch(HandshakeError):
    """
    Raised if the RTMP header bytes mismatch.
    """


class HandshakeVerificationError(HandshakeError):
    """
    Raised if the handshake verification failed.
    """


class IHandshakeObserver(Interface):
    """
    Observes handshake events.
    """

    def handshakeSuccess():
        """
        Handshaking was successful.
        """

    def handshakeFailure(reason):
        """
        Handshaking failed.

        @param reason: Why the handshake failed.
        @type reason: Exception wrapped L{Failure}
        """

    def write(data):
        """
        Called when the handshake negotiator writes some data.
        """


class IHandshakeNegotiator(Interface):
    """
    Negotiates handshakes.
    """

    observer = Attribute(
        "An L{IHandshakeObserver} that listens for events from this " \
        "negotiator")
    server = Attribute(
        "The server handshake token. Can be L{ServerToken} or C{None}")
    client = Attribute(
        "The client handshake token. Can be L{ServerToken} or C{None}")

    def start(uptime=None, version=None):
        """
        Called to start the handshaking process. You can supply the uptime and
        version, otherwise they will be worked out automatically. The version
        specifically will be set to enable H.264 streaming.
        """

    def dataReceived(self, data):
        """
        Called when handshaking data has been received.
        """


class Token(object):
    """
    Base functionality for handshake tokens.

    @ivar uptime: The number of milliseconds since the last reboot.
    @type uptime: C{int}
    @ivar version: The api version for the handshake. This is used for check
        for H.264 support.
    @type version: C{int} or L{versions.Version}
    @ivar context: The context for this handshake. This is used for RTMPE
        support. A value C{None} means that normal RTMP streaming should
        commence. Defaults to C{None}.
    @note: L{context} is not used at the moment (until we get RTMPE support).
    @ivar payload: A place to dump unknown bytes to complete the handshake. If
        this is C{None} then the payload will be generated.
    @type payload: C{None} or L{util.BufferedByteStream}
    """

    def __init__(self, uptime=0, version=0, context=None, payload=None):
        self.uptime = uptime
        self.version = version
        self.context = context
        self.payload = None

        if payload is not None:
            self.payload = util.BufferedByteStream(payload)

    def encode(self):
        """
        Called to encode the token to a byte string.
        """
        if self.payload is None:
            self.generatePayload()

        return self.payload.getvalue()

    def generatePayload(self):
        """
        Generates the payload for the handshake token. Must be implemented by
        sub classes. The implementor must set the internal pointer of the
        payload to the beginning.
        """
        raise NotImplementedError

    def __str__(self):
        return self.encode()

    def __cmp__(self, other):
        return cmp(str(self), str(other))


class ClientToken(Token):
    """
    Represents a decoded client handshake.
    """

    def generatePayload(self):
        if self.payload is not None:
            return

        self.payload = util.BufferedByteStream()

        self.payload.write_ulong(self.uptime)
        self.payload.write_ulong(self.version)
        self.payload.write(generateBytes(HANDSHAKE_LENGTH - 8))
        self.payload.seek(0)

    def getDigest(self):
        """
        Returns an SHA-256 HMAC based on the payload. If the L{version} of
        this token is less than L{versions.H264_MIN_FLASH} then
        C{None} will be returned.

        @rtype: C{str} or C{None}
        @raise HandshakeError: No payload exists
        """
        if hasattr(self, '_digest'):
            return self._digest

        if self.payload is None:
            raise HandshakeError('No digest available for an empty handshake')

        if self.version < versions.H264_MIN_FLASH:
            return None

        b = self.payload
        pos = b.tell()
        b.seek(8)

        s = sum([b.read_char() for x in xrange(0, 4)])
        b.seek(s % 728 + 12)

        self._digest = b.read(32)
        b.seek(pos)

        return self._digest


class ServerToken(Token):
    """
    Represents a decoded server handshake.

    @ivar client: The client handshake token.
    @type client: L{ClientToken}
    """

    def __init__(self, client, *args, **kwargs):
        Token.__init__(self, *args, **kwargs)

        self.client = client

    def generatePayload(self):
        """
        Generates a payload that is sensitive to the client payload. If the
        client does not have a valid digest (read:C{None}) then some random
        bytes will be generated.
        """
        if self.payload is not None:
            return

        self.payload = util.BufferedByteStream()

        self.payload.write_ulong(self.uptime)
        self.payload.write_ulong(self.version)

        if self.client.getDigest() is None:
            self.payload.write(generateBytes(HANDSHAKE_LENGTH - 8))
            self.payload.write(self.client.encode())
            self.payload.seek(0)

            return

        self.payload.write(generateBytes(
            HANDSHAKE_LENGTH - 8 - SHA256_DIGEST_LENGTH))

        digest = self.getDigest()

        if digest is None:
            raise HandshakeError('Client not H.264 compatible')

        client = self.client.encode()
        self.payload.seek(0, 2)
        self.payload.write(_digest(digest, client) + client)
        self.payload.seek(0)

    def getDigest(self):
        """
        Returns an SHA-256 HMAC based on the payload. If the L{version} of
        this token is less than L{versions.H264_MIN_FMS} then
        C{None} will be returned.

        @rtype: C{str} or C{None}
        @raise HandshakeError: No payload exists.
        """
        if hasattr(self, '_digest'):
            return self._digest

        if self.payload is None:
            raise HandshakeError('No digest available for an empty handshake')

        if self.version < versions.H264_MIN_FMS:
            return None

        client_digest = self.client.getDigest()

        if client_digest is None:
            return None

        self._digest = _digest(SECRET_SERVER_KEY, self.payload.getvalue())

        return self._digest


class BaseNegotiator(object):
    """
    Abstract functionality for negotiating an RTMP handshake.

    @ivar observer: An observer for handshake negotiations.
    @type observer: L{IHandshakeObserver}
    @ivar server: The server token.
    @type server: L{ServerToken}
    @ivar client: The client token.
    @type client: L{ClientToken}
    @ivar buffer: Any data that has not yet been consumed.
    """

    implements(IHandshakeNegotiator)

    buffer = ''
    server = None
    client = None
    started = False

    def __init__(self, observer):
        if not IHandshakeObserver.providedBy(observer):
            raise TypeError('IHandshakeObserver interface ' \
                'expected (got:%s)' % (type(observer),))

        self.observer = observer

    def dataReceived(self, data):
        """
        Called when Implemented by concrete subclasses.
        """
        raise NotImplementedError


class ClientNegotiator(BaseNegotiator):
    """
    Negotiator for client initiating handshakes.
    """

    def start(self, uptime=None, version=None):
        """
        Called to start the handshaking negotiations. Writes the header byte
        and client payload to the observer.

        @param uptime: The number of milliseconds since the system booted.
            See L{Token.uptime}.
        @param version: The version of the connecting client.
        """
        self.uptime = uptime
        self.version = version

        self.generateToken()

        self.client_payload = self.client.encode()
        self.header = getHeader(self.client)
        self.received_header = None

        self.observer.write(self.header + self.client_payload)

    def generateToken(self):
        """
        An internal method that generates a client token.
        """
        uptime, version = self.uptime, self.version

        if uptime is None:
            uptime = util.uptime()

        if version is None:
            version = versions.H264_MIN_FLASH

        if version < versions.H264_MIN_FLASH:
            version = 0

        self.client = ClientToken(uptime, version)

    def _dataReceived(self, data):
        data = self.buffer + data

        if self.received_header is None:
            if len(data) < 1:
                self.buffer = data

                return

            self.received_header = data[0]

            if self.header != self.received_header:
                raise HeaderMismatch('My header = %r, received header = ' \
                    '%r' % (self.header, self.received_header))

            data = data[1:]

        if self.server is None:
            if len(data) < HANDSHAKE_LENGTH:
                self.buffer = data

                return

            self.server = decodeServerHandshake(self.client, data)
            data = data[HANDSHAKE_LENGTH:]

        # we now have a valid server token, we are now expecting to have our
        # original client token

        if len(data) < HANDSHAKE_LENGTH:
            self.buffer = data

            return

        if self.client_payload != data[:HANDSHAKE_LENGTH]:
            raise HandshakeVerificationError

        # if we get here then a successful handshake has been negotiated.
        # inform the observer accordingly
        self.observer.handshakeSuccess()

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{handshakeFailure} will be
        called.
        """
        try:
            self._dataReceived(data)
        except:
            self.observer.handshakeFailure(Failure())


class ServerNegotiator(BaseNegotiator):
    """
    Negotiator for server handshakes.
    """

    def start(self, uptime=None, version=None):
        """
        Called to start the handshaking negotiations. Writes the header byte
        and client payload to the observer.

        @param uptime: The number of milliseconds since the system booted.
            See L{Token.uptime}.
        @param version: The version of the connecting client.
        """
        self.uptime = uptime
        self.version = version
        self.header = None
        self.received_header = None
        self.started = True

    def generateToken(self):
        """
        Generate a server handshake token.
        """
        if not self.started:
            raise HandshakeError('`start` must be called before generating ' \
                'server token')

        if self.client is None:
            raise HandshakeError('client token is required before ' \
                'generating server token')

        uptime = self.uptime
        version = self.version
        client = self.client

        if uptime is None:
            uptime = util.uptime()

        if version is None:
            version = versions.H264_MIN_FMS

        if version < versions.H264_MIN_FMS:
            version = 0

        self.server = ServerToken(client, uptime, version)

    def _dataReceived(self, data):
        data = self.buffer + data

        if self.received_header is None:
            if len(data) < 1:
                self.buffer = data

                return

            self.received_header = data[0]

            data = data[1:]

        if len(data) < HANDSHAKE_LENGTH:
            self.buffer = data

            return

        if len(data) > HANDSHAKE_LENGTH:
            raise HandshakeError('Unexpected trailing data in client ' \
                'handshake')

        self.client = decodeClientHandshake(data)

        self.generateToken()
        self.header = getHeader(self.client)
        self.server_payload = self.server.encode()

        self.observer.write(
            self.header + self.server_payload)

        # at this point, as far as the server is concerned, handshaking has
        # been successful
        self.observer.handshakeSuccess()

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{handshakeFailure} will be
        called.
        """
        try:
            self._dataReceived(data)
        except:
            self.observer.handshakeFailure(Failure())


def decodeClientHandshake(data):
    """
    Builds a L{ClientToken} based on the supplied C{data}.

    @type data: C{str}
    @return: The decoded client token.
    @rtype: L{ClientToken}
    @raise EOFError: Not enough data supplied to fully decode token.
    """
    s = util.BufferedByteStream(data)

    uptime = s.read_ulong()
    version = versions.Version(s.read_ulong())

    try:
        payload = s.read(HANDSHAKE_LENGTH - 8)
    except IOError, e:
        raise EOFError(str(e))

    return ClientToken(uptime=uptime, version=version, payload=payload)


def decodeServerHandshake(client, data):
    """
    Builds a L{ServerToken} based on the supplied C{data}.

    @type data: C{str}
    @return: The decoded server token.
    @rtype: L{ServerToken}
    @raise EOFError: Not enough data supplied to fully decode token.
    """
    s = util.BufferedByteStream(data)

    uptime = s.read_ulong()
    version = versions.Version(s.read_ulong())

    try:
        payload = s.read(HANDSHAKE_LENGTH - 8)
    except IOError, e:
        raise EOFError(str(e))

    return ServerToken(client, uptime=uptime, version=version, payload=payload)


def generateBytes(length):
    """
    Generates a string of C{length} bytes of pseudo-random data. Used for 
    filling in the gaps in unknown sections of the handshake.

    This function is going to to called a lot and is ripe for moving into C.

    @param length: The number of bytes to generate.
    @type length: C{int}
    @return: A random string of bytes, length C{length}.
    @rtype: C{str}
    """
    # FIXME: sloooow
    if not isinstance(length, (int, long)):
        raise TypeError('int expected for length (got:%s)' % (type(length),))

    bytes = ''

    for x in xrange(0, length):
        bytes += chr(random.randint(0, 0xff))

    return bytes


def _digest(key, payload):
    """
    A helper method that wraps generating a SHA-256 HMAC digest.

    @param key: The key to use in generating the digest.
    @type key: C{str}
    @param payload: The message to digest.
    @type payload: C{str}
    @return: A hexdigest representation of the digested message.
    @rtype: C{str}
    """
    return hmac.new(key, msg=payload, digestmod=hashlib.sha256).digest()


def getHeader(token):
    """
    Returns an RTMP header byte based on the supplied token.

    @param token: The handshake token.
    @type token: L{Token}
    @return: The relevant header byte.
    @rtype: C{str}
    """
    if token.context is not None:
        return RTMPE_HEADER_BYTE

    return RTMP_HEADER_BYTE
