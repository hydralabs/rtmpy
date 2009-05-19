# -*- test-case-name: rtmpy.tests.rtmp.test_handshake -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP handshake support.

@see: U{RTMP Handshake on RTMPy wiki (external)
      <http://rtmpy.org/wiki/RTMP#a3.Handshake>}
@since: 0.1
"""

import hmac, hashlib
from zope.interface import implements
from twisted.python.failure import Failure

from rtmpy import versions, util, rtmp
from rtmpy.rtmp import interfaces


SERVER_KEY = \
    '\x47\x65\x6e\x75\x69\x6e\x65\x20\x41\x64\x6f\x62\x65\x20\x46\x6c\x61' \
    '\x73\x68\x20\x4d\x65\x64\x69\x61\x20\x53\x65\x72\x76\x65\x72\x20\x30' \
    '\x30\x31\xf0\xee\xc2\x4a\x80\x68\xbe\xe8\x2e\x00\xd0\xd1\x02\x9e\x7e' \
    '\x57\x6e\xec\x5d\x2d\x29\x80\x6f\xab\x93\xb8\xe6\x36\xcf\xeb\x31\xae'

HANDSHAKE_LENGTH = 1536
SHA256_DIGEST_LENGTH = 64

RTMP_HEADER_BYTE = '\x03'
RTMPE_HEADER_BYTE = '\x06'

HEADER_BYTES = [RTMP_HEADER_BYTE, RTMPE_HEADER_BYTE]


class HandshakeError(rtmp.BaseError):
    """
    Generic class for handshaking related errors.
    """


class HeaderMismatch(HandshakeError):
    """
    Raised if the RTMP header bytes mismatch.
    """


class VerificationError(HandshakeError):
    """
    Raised if the handshake verification failed.
    """


class Token(object):
    """
    Base functionality for handshake tokens. A token must be able to generate
    its own payload if necessary.

    @ivar uptime: The number of milliseconds since the last reboot.
    @type uptime: C{int}
    @ivar version: The api version for the handshake. This is used for check
        for H.264 support.
    @type version: C{int} or L{versions.Version}
    @ivar context: The context for this handshake. This is used for RTMPE
        support. A value C{None} means that normal RTMP streaming should
        commence. Defaults to C{None}.
    @note: L{context} is not used at the moment (until we get RTMPE support).
    """

    def __init__(self, uptime=0, version=0, context=None, payload=None):
        self.uptime = uptime
        self.version = version
        self.context = context
        self._payload = None

        if payload is not None:
            self._payload = util.BufferedByteStream(payload)

    def encode(self):
        """
        Called to encode the token to a byte string.
        """
        if self._payload is None:
            self.generatePayload()

        return self._payload.getvalue()

    def generatePayload(self):
        """
        Generates the payload for the handshake token. Must be implemented by
        sub classes. The implementor must set the internal pointer of the
        payload to the beginning.
        """
        raise NotImplementedError()

    def __str__(self):
        return self.encode()

    def __cmp__(self, other):
        return cmp(str(self), str(other))

    def __repr__(self):
        attrs = ['uptime', 'version', 'context']

        s = ['%s=%r' % (k, getattr(self, k)) for k in attrs]

        return '<%s.%s %s at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            ' '.join(s),
            id(self))


class ClientToken(Token):
    """
    Represents a client handshake token.
    """

    def generatePayload(self):
        """
        Generate a client handshake payload if one doesn't already exist.
        """
        if self._payload is not None:
            return

        self._payload = util.BufferedByteStream()

        self._payload.write_ulong(self.uptime)
        self._payload.write_ulong(int(self.version))
        self._payload.write(util.generateBytes(HANDSHAKE_LENGTH - 8))
        self._payload.seek(0)

    def getDigest(self):
        """
        Returns an SHA-256 HMAC based on the payload. If the L{version} of
        this token is less than L{versions.H264_MIN_FLASH} then C{None} will
        be returned.

        @rtype: C{str} or C{None}
        @raise HandshakeError: No payload exists
        """
        if hasattr(self, '_digest'):
            return self._digest

        if self._payload is None:
            raise HandshakeError('No digest available for an empty handshake')

        if self.version < versions.H264_MIN_FLASH:
            return None

        b = self._payload
        pos = b.tell()
        b.seek(8)

        s = sum([b.read_char() for x in xrange(0, 4)])
        b.seek(s % 728 + 12)

        self._digest = b.read(32)
        b.seek(pos)

        return self._digest


class ServerToken(Token):
    """
    Represents a server handshake.

    @ivar client: The received client handshake token.
    @type client: L{ClientToken}
    """

    def __init__(self, client, *args, **kwargs):
        Token.__init__(self, *args, **kwargs)

        self.client = client

    def generatePayload(self):
        """
        Generates a payload that is contextually dependant on the client
        payload. If the client does not have a valid digest (read:C{None})
        then some random bytes will be generated.
        """
        if self._payload is not None:
            return

        self._payload = util.BufferedByteStream()

        self._payload.write_ulong(self.uptime)
        self._payload.write_ulong(int(self.version))

        if self.client.getDigest() is None:
            self._payload.write(util.generateBytes(HANDSHAKE_LENGTH - 8))
            self._payload.write(self.client.encode())
            self._payload.seek(0)

            return

        self._payload.write(util.generateBytes(
            HANDSHAKE_LENGTH - 8 - SHA256_DIGEST_LENGTH))

        digest = self.getDigest()

        if digest is None:
            digest = util.generateBytes(SHA256_DIGEST_LENGTH)

        client = self.client.encode()
        self._payload.seek(0, 2)
        self._payload.write(_digest(digest, client) + client)
        self._payload.seek(0)

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

        if self._payload is None:
            raise HandshakeError('No digest available for an empty handshake')

        if self.version < versions.H264_MIN_FMS:
            return None

        client_digest = self.client.getDigest()

        if client_digest is None:
            return None

        self._digest = _digest(SERVER_KEY, self._payload.getvalue())

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

    implements(interfaces.IHandshakeNegotiator)

    def __init__(self, observer):
        """
        @raise TypeError: L{interfaces.IHandshakeObserver} expected for
            C{observer}.
        """
        if not interfaces.IHandshakeObserver.providedBy(observer):
            raise TypeError('IHandshakeObserver interface ' \
                'expected (got:%s)' % (type(observer),))

        self.observer = observer

        self.buffer = ''
        self.server = None
        self.client = None
        self.started = False

        self.debug = rtmp.DEBUG

    def dataReceived(self, data):
        """
        Called when Implemented by concrete subclasses.
        
        @raise NotImplementedError:
        """
        raise NotImplementedError()


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
        @raise HandshakeError: Once started, handshake negotiator cannot be
            re-started.
        """
        if self.started:
            raise HandshakeError(
                'Once started, handshake negotiator cannot be re-started.')

        self.started = True
        self.uptime = uptime
        self.version = version

        self.generateToken()

        if self.debug or rtmp.DEBUG:
            rtmp.log(self, 'client token = %r' % (self.client,))

        self.clientPayload = self.client.encode()
        self.header = getHeader(self.client)
        self.receivedHeader = None

        self.observer.write(self.header + self.clientPayload)

    def generateToken(self):
        """
        An internal method that generates a client token.
        
        @raise HandshakeError: L{start} must be called before generating server
            token.
        """
        if not self.started:
            raise HandshakeError(
                '`start` must be called before generating server token')

        uptime, version = self.uptime, self.version

        if uptime is None:
            uptime = util.uptime()

        if version is None:
            version = versions.H264_MIN_FLASH

        if version < versions.H264_MIN_FLASH:
            version = 0

        self.client = ClientToken(uptime, version)

    def _dataReceived(self, data):
        """
        @raise HandshakeError: Unknown header byte.
        @raise HeaderMismatch: Headers don't match.
        """
        data = self.buffer + data

        if self.receivedHeader is None:
            if len(data) < 1:
                self.buffer = data

                return

            self.receivedHeader = data[0]

            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Received header = %r' % (self.receivedHeader,))

            if self.receivedHeader not in HEADER_BYTES:
                raise HandshakeError(
                    'Unknown header byte %r' % (self.receivedHeader,))

            if self.header != self.receivedHeader:
                raise HeaderMismatch('My header %r, received header %r' % (
                    self.header, self.receivedHeader))

            data = data[1:]

        if self.server is None:
            if len(data) < HANDSHAKE_LENGTH:
                self.buffer = data

                return

            self.server = decodeServerHandshake(self.client, data[:HANDSHAKE_LENGTH])
            data = data[HANDSHAKE_LENGTH:]

            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Decoded server token = %r' % (self.server,))

        # we now have a valid server token, we are now expecting to have our
        # original client token

        if len(data) < HANDSHAKE_LENGTH:
            self.buffer = data

            return

        if self.clientPayload != data[:HANDSHAKE_LENGTH]:
            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Client payload = (len:%d) %r' % (
                    len(self.clientPayload), self.clientPayload,))
                rtmp.log(self, 'Received data = (len:%d) %r' % (
                    len(data[:HANDSHAKE_LENGTH]), data[:HANDSHAKE_LENGTH],))

            raise VerificationError()

        # if we get here then a successful handshake has been negotiated.
        # inform the observer accordingly
        self.observer.handshakeSuccess()

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{handshakeFailure} will be
        called.
        
        @raise HandshakeError: Data received, but not L{started} yet.
        """
        try:
            if not self.started:
                raise HandshakeError('Data received, but not started')

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
        @type uptime: C{int} or C{None}
        @param version: The version of the connecting client.
        @type version: C{int} or C{rtmpy.versions.Version} or C{None}
        """
        self.uptime = uptime
        self.version = version
        self.header = None
        self.receivedHeader = None
        self.started = True

    def generateToken(self):
        """
        Generate a server handshake token.
        
        @raise HandshakeError: `start` must be called before generating server
            token.
        @raise HandshakeError: 'client token is required before generating
            server token.
        """
        if not self.started:
            raise HandshakeError(
                '`start` must be called before generating server token')

        if self.client is None:
            raise HandshakeError(
                'client token is required before generating server token')

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
        """
        @raise HandshakeError: Unknown header byte.
        @raise HandshakeError: Unexpected trailing data in client handshake.
        """
        data = self.buffer + data

        if self.receivedHeader is None:
            if len(data) < 1:
                return

            self.receivedHeader = data[0]

            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Received header %r' % (self.receivedHeader,))

            if self.receivedHeader not in HEADER_BYTES:
                raise HandshakeError(
                    'Unknown header byte %r' % (self.receivedHeader,))

            data = data[1:]

        if len(data) < HANDSHAKE_LENGTH:
            self.buffer = data

            return

        if self.client is None:
            if len(data) > HANDSHAKE_LENGTH:
                raise HandshakeError(
                    'Unexpected trailing data in client handshake')

            self.client = decodeClientHandshake(data)

            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Decoded client token = %r' % (self.client,))

            self.generateToken()
            self.header = getHeader(self.client)
            self.serverPayload = self.server.encode()

            if self.debug or rtmp.DEBUG:
                rtmp.log(self, 'Server token = %r' % (self.server,))

            self.observer.write(self.header + self.serverPayload)

            data = ''

        if len(data) < HANDSHAKE_LENGTH:
            self.buffer = data

            return

        self.buffer = data[HANDSHAKE_LENGTH:]
        # at this point, as far as the server is concerned, handshaking has
        # been successful

        self.observer.handshakeSuccess()

    def dataReceived(self, data):
        """
        Called when handshake data has been received. If an error occurs
        whilst negotiating the handshake then C{handshakeFailure} will be
        called, citing the reason.
        
        @raise HandshakeError: Data received, but not started.
        """
        try:
            if not self.started:
                raise HandshakeError('Data received, but not started')

            self._dataReceived(data)
        except:
            self.observer.handshakeFailure(Failure())


def decodeClientHandshake(data):
    """
    Builds a L{ClientToken} based on the supplied C{data}.

    @type data: C{str}
    @return: The decoded client token.
    @rtype: L{ClientToken}
    @raise HandshakeError: Not enough data supplied to fully decode token.
    """
    s = util.BufferedByteStream(data)

    try:
        uptime = s.read_ulong()
        version = versions.Version(s.read_ulong())
        s.seek(0)

        payload = s.read(HANDSHAKE_LENGTH)
    except IOError:
        raise HandshakeError('Not enough data to decode a full client token')

    return ClientToken(uptime=uptime, version=version, payload=payload)


def decodeServerHandshake(client, data):
    """
    Builds a L{ServerToken} based on the supplied C{data}.

    @param client: The client token.
    @type client: L{ClientToken}
    @type data: C{str}
    @return: The decoded server token.
    @rtype: L{ServerToken}
    @raise HandshakeError: Not enough data to decode a full server token.
    """
    s = util.BufferedByteStream(data)

    try:
        uptime = s.read_ulong()
        version = versions.Version(s.read_ulong())
        s.seek(0)

        payload = s.read(HANDSHAKE_LENGTH)
    except IOError:
        raise HandshakeError('Not enough data to decode a full server token')

    return ServerToken(client, uptime=uptime, version=version, payload=payload)


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
