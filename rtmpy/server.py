# -*- test-case-name: rtmpy.tests.test_server -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Server implementation.

@since: 0.1.0
"""

from zope.interface import Interface, Attribute, implements

from twisted.internet import reactor, protocol, defer
from twisted.python import log
from twisted.application import internet
import pyamf

from rtmpy import rtmp, util, dispatcher


class Client:
    """
    Represents a user or client to an application instance. A client object is
    unique to each application.
    """

    def __init__(self, stream, **kwargs):
        self.__dict__.update(kwargs)
        self.stream = stream

    def connectionAccepted(self, application):
        self.application = application

class ServerProtocol(rtmp.BaseProtocol):
    """
    Server RTMP Protocol.
    """

    def _decodeHandshake(self):
        """
        Negotiates the handshake phase of the protocol.

        @see: U{RTMP handshake on OSFlash (external)
        <http://osflash.org/documentation/rtmp#handshake>} for more info.
        """
        buffer = self.buffer

        if self.my_handshake is not None:
            # we have received the correct header, the peer's handshake,
            # sent our own handshake, time to validate.
            if buffer.remaining() < rtmp.HANDSHAKE_LENGTH:
                return

            hs = buffer.read(rtmp.HANDSHAKE_LENGTH)

            if hs[8:] != self.my_handshake[8:]:
                self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Handshake mismatch')

                return

            self.dispatchEvent(rtmp.HANDSHAKE_SUCCESS)

            return

        # check there is enough data to proceed ..
        if self.received_handshake is not None:
            if len(buffer) < rtmp.HANDSHAKE_LENGTH:
                return
        else:
            if len(buffer) < 1:
                return

        buffer.seek(0)

        if self.received_handshake is None and buffer.read(1) != rtmp.HEADER_BYTE:
            self.dispatchEvent(rtmp.HANDSHAKE_FAILURE, 'Invalid header byte received')

            return

        self.received_handshake = ''

        if buffer.remaining() < rtmp.HANDSHAKE_LENGTH:
            return

        self.received_handshake = buffer.read(rtmp.HANDSHAKE_LENGTH)
        self.my_handshake = rtmp.generate_handshake()

        self.transport.write(
            rtmp.HEADER_BYTE + self.my_handshake + self.received_handshake)

    def decodeHandshake(self, data):
        self.buffer.seek(0, 2)
        self.buffer.write(data)
        self.buffer.seek(0)
        self._decodeHandshake()
        self.buffer.consume()

    def onHandshakeSuccess(self):
        """
        Successful handshake between server and client.
        """
        rtmp.BaseProtocol.onHandshakeSuccess(self)

        self.addEventListener('connect', self.onConnect)

        if len(self.buffer) > 0:
            bytes = self.buffer.getvalue()
            self.buffer.truncate()

            self._callLater(0, self.dataReceived, bytes)

    def onConnect(self, command):
        """
        Called when the peer sends a C{connect} request.
        """
        print command
        def return_response(result, c, a):
            if c.application is a:
                command.setResult(None, {
                    'level': 'status',
                    'code': 'NetConnection.Connect.Success',
                    'description': 'Connection succeeded.',
                })
                command.complete()

        app = self.factory.getApplication(command['app'])
        client = Client(self.core_stream, agent=command['flashVer'],
            pageurl=command['pageUrl'], referrer=command['swfUrl'],
            protocol=command['tcUrl'].split(':', 1)[0])

        d = defer.maybeDeferred(app.onConnect, client)

        d.addCallback(return_response, client, app)


class IApplication(Interface):

    clients = Attribute("A list of all clients currently connected to the application.")
    name = Attribute("The name of the application instance.")

    def startup():
        """
        Called when the server loads the application. Can return a deferred
        that signals that the application has fully initialized. Once startup
        is complete, the L{onAppStartup} event must be fired.
        """

    def shutdown():
        """
        Called when the application is unloaded. Can return a deferred that
        signals that the application has completely shutdown. Use this to close
        database connections etc. When this function is called, the
        L{onAppShutdown} must be be called.
        """

    def rejectConnection(client, reason):
        """
        Rejects the connection from the client, C{reason} being a
        L{failure.Failure} object or a string. Once the client has been
        rejected, the connection to the client must be closed.
        """

    def acceptConnection(client):
        """
        Called when the client has been accepted by this application. The event
        L{onConnectAccept}.
        """

    def disconnect(client):
        """
        Disconnects a client from the application. Must fire a L{onDisconnect}.
        Returns a deferred that results in the outcome of the disconnection.
        """


class Application:
    implements(IApplication)

    clients = []

    def startup(self):
        """
        Called when the application is starting up.
        """

    def shutdown(self):
        """
        Called when the application is closed.
        """

    def rejectConnection(self, client):
        """
        Called when a client connection request has been rejected.
        """
        # reject the connection and close
        # client.onStatus(...)
        client.close()

    def acceptConnection(self, client):
        """
        Called when this application has accepted the client connection. 
        """
        self.clients.append(client)
        client.connectionAccepted(self)

        # client.dispatchEvent(status 

    def disconnect(self, client):
        """
        Removes the C{client} from this application.
        """
        self.clients.remove(client)
        # close the connection with the client
        client.close()

    def onConnect(self, client):
        """
        Called when a client attempts to attach itself to this application.
        """
        self.acceptConnection(client)


class ServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory.
    """

    protocol = ServerProtocol

    def __init__(self, applications):
        self.applications = applications

        for app in self.applications.values():
            app.startup()

    def getApplication(self, name):
        """
        Returns the application mounted at C{name}, if any.
        """
        return self.applications.get(name, None)

    def buildProtocol(self, addr):
        p = protocol.ServerFactory.buildProtocol(self, addr)
        p.debug = True

        return p

class RTMPServer(internet.TCPServer):
    """
    Twisted RTMP server.
    """
    
    factoryClass = ServerFactory

    def __init__(self, port, applications=None):
        if applications is None:
            applications = {}

        internet.TCPServer.__init__(self, port, self.factoryClass(applications))    
