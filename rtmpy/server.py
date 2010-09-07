# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Server implementation.
"""

from zope.interface import Interface, Attribute, implements
from twisted.internet import protocol, defer, reactor
import pyamf

from rtmpy import util, exc
from rtmpy.protocol.rtmp import message
from rtmpy.protocol import rtmp, handshake, version


class ServerControlStream(rtmp.ControlStream):
    """
    """

    def __init__(self, protocol, streamId):
        rtmp.ControlStream.__init__(self, protocol, streamId)

        self.application = self.protocol.application

    def onConnect(self, args):
        def cb(res):
            """
            Called when the connect packet has been accepted by the application.
            """
            oE = args.pop('objectEncoding', self.protocol.objectEncoding)

            self.protocol.objectEncoding = oE
            f = self.protocol.factory

            self.sendMessage(
                message.DownstreamBandwidth(f.downstreamBandwidth))
            self.sendMessage(
                message.UpstreamBandwidth(f.upstreamBandwidth, 2))
            self.sendMessage(
                message.ControlMessage(0, 0))

            return {
                'code': 'NetConnection.Connect.Success',
                'description': 'Connection succeeded.',
                'objectEncoding': self.protocol.objectEncoding
            }

        def eb(fail):
            """
            Called when an error occurred when asking the application to validate
            the connection request.
            """
            code = getattr(fail.type, 'code', 'NetConnection.Connect.Failed')
            description = fail.getErrorMessage() or 'Internal Server Error'

            self.sendStatus(code, level='error', description=description)

            return fail

        d = defer.maybeDeferred(self.protocol.onConnect, *(args,))

        d.addErrback(eb).addCallback(cb)

        return d

    def getInvokableTarget(self, name):
        if self.application is None:
            if name == 'connect':
                return self.onConnect


class IApplication(Interface):
    """
    """

    clients = Attribute("A collection of clients connected to this application.")
    name = Attribute("The name of the application instance.")
    factory = Attribute("The Factory instance that this application is"
        "attached to.")

    def startup():
        """
        Called when the server loads the application instance. Can return a
        deferred that signals that the application has fully initialized.
        """

    def shutdown():
        """
        Called when the application is unloaded. Can return a deferred that
        signals that the application has completely shutdown. Use this to
        close database connections etc.
        """

    def rejectConnection(client, reason):
        """
        Rejects the connection from the client, C{reason} being a
        L{failure.Failure} object or a string. Once the client has been
        rejected, the connection to the client must be closed.
        """

    def acceptConnection(client):
        """
        Called when the client connection request has been accepted by this
        application.
        """

    def disconnect(client, reason=None):
        """
        Disconnects a client from the application. Returns a deferred that is
        called when the disconnection was successful.
        """


class Client(object):
    """
    """

    def __init__(self):
        self.protocol = None
        self.application = None

        self.pendingCalls = []

    def call(self, name, *args):
        """
        """
        d = defer.Deferred()

        if args == ():
            args = (None,)

        if self.application is None:
            self.pendingCalls.append((name, args, d))

            return d

        s = self.protocol.getStream(0)
        x = s.sendMessage(message.Invoke(name, 0, *args), channelId=3)

        x.addCallback(lambda _: d.callback(pyamf.Undefined))

        return d

    def registerApplication(self, application):
        """
        """
        self.application = application
        s = self.protocol.getStream(0)

        for name, args, d in self.pendingCalls:
            x = s.writeEvent(event.Invoke(name, 0, *args), channelId=3)

            x.chainDeferred(d)

        self.pendingCalls = []

    def disconnect(self):
        """
        Disconnects the client. Returns a deferred to signal when this client
        has disconnected.
        """
        def cb(_):
            self.application.onDisconnect(self)
            self.protocol.transport.loseConnection()
            self.protocol = None
            self.application = None

        s = self.protocol.getStream(0)
        d = s.sendStatus(code='NetConnection.Connection.Closed',
            description='Client disconnected.')

        d.addCallback(cb)

        return d

    def checkBandwidth(self):
        pass


class Application(object):
    """
    """

    implements(IApplication)

    client = Client

    def __init__(self):
        self.clients = {}
        self.streams = {}

    def startup(self):
        """
        Called when the application is starting up.
        """

    def shutdown(self):
        """
        Called when the application is closed.
        """

    def connectionAccepted(self, client):
        """
        Called when this application has accepted the client connection.
        """
        clientId = util.generateBytes(9, readable=True)
        client.id = clientId

        self.clients[client] = clientId
        self.clients[clientId] = client

    def disconnect(self, client):
        """
        Removes the C{client} from this application.
        """
        try:
            del self.clients[client]
            del self.clients[client.id]
        except KeyError:
            pass

        client.id = None

    def buildClient(self, protocol):
        """
        Create an instance of a subclass of L{Client}. Override this method to
        alter how L{Client} instances are created.

        @param protocol: The L{rtmp.ServerProtocol} instance.
        """
        c = self.client()
        c.protocol = protocol

        return c

    def onConnect(self, client, **kwargs):
        """
        Called when a connection request is made to this application. Must
        return a C{bool} (or a L{defer.Deferred} returning a C{bool}) which
        determines the result of the connection request.

        If C{False} is returned (or an exception raised) then the connection is
        rejected.

        @param client: The client requesting the connection.
        @type client: An instance of L{client_class}.
        @param kwargs: The arguments supplied as part of the connection
            request.
        @type kwargs: C{dict}
        """

    def onPublish(self, client, stream):
        """
        Called when a client attempts to publish to a stream.
        """

    def onUnpublish(self, client, stream):
        """
        Called when a client unpublishes a stream.
        """

    def onDisconnect(self, client):
        """
        Called when a client disconnects.
        """
        self.disconnect(client)


class ServerProtocol(rtmp.RTMPProtocol):
    """
    A basic RTMP protocol that will act like a server.
    """

    def onConnect(self, args):
        """
        Called when a 'connect' packet is received from the client.
        """
        if self.application:
            # This protocol has already successfully completed a connection
            # request.
            raise exc.ConnectFailed('Already connected.')

        try:
            appName = args['app']
        except KeyError:
            raise exc.ConnectFailed("Bad connect packet (missing 'app' key)")

        self.application = self.factory.getApplication(appName)

        if self.application is None:
            raise exc.InvalidApplication('Unknown application %r' % (appName,))

        self.client = self.application.buildClient(self)

        def cb(res):
            if res is False:
                raise exc.ConnectRejected('Authorization is required')

            self.application.connectionAccepted(self.client)

        def eb(f):
            print 'failed app.onConnect', f
            return status.status(
                code='NetConnection.Connect.Failed',
                description='Internal Server Error'
            )

        d = defer.maybeDeferred(self.application.onConnect, self.client, **args)

        d.addCallback(cb)

        return d


class ServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory.

    Maintains a collection of applications that RTMP clients connect and
    interact with.

    @ivar applications: A collection of active applications.
    @type applications: C{dict} of C{name} -> L{IApplication}
    @ivar _pendingApplications: A collection of applications that are pending
        activation.
    @type _pendingApplications: C{dict} of C{name} -> L{IApplication}
    """

    protocol = ServerProtocol
    protocolVersion = version.RTMP

    upstreamBandwidth = 2500000L
    downstreamBandwidth = 2500000L
    fmsVer = u'FMS/3,5,1,516'

    def __init__(self, applications=None):
        self.applications = {}
        self._pendingApplications = {}

        if applications:
            for name, app in applications.items():
                self.registerApplication(name, app)

    def getControlStream(self, protocol, streamId):
        """
        Creates and returns the stream for controlling server side protocol
        instances.

        @param protocol: The L{ServerProtocol} instance created by
            L{buildProtocol}
        @param streamId: The streamId for this control stream. Always 0.
        """
        return ServerControlStream(protocol, streamId)

    def getApplication(self, name):
        """
        Returns the active L{IApplication} instance related to C{name}. If
        there is no active application, C{None} is returned.
        """
        return self.applications.get(name, None)

    def registerApplication(self, name, app):
        """
        Registers the application to this factory instance. Returns a deferred
        which will signal the completion of the registration process.

        @param name: The name of the application. This is the name that the
            player will use when connecting to this server. An example::

            RTMP uri: http://appserver.mydomain.com/webApp; name: webApp.
        @param app: The L{IApplication} object that will interact with the
            RTMP clients.
        @return: A deferred signalling the completion of the registration
            process.
        """
        if name in self._pendingApplications or name in self.applications:
            raise exc.InvalidApplication(
                '%r is already a registered application' % (name,))

        self._pendingApplications[name] = app

        d = defer.maybeDeferred(app.startup)

        def cleanup_pending(r):
            try:
                del self._pendingApplications[name]
            except KeyError:
                raise exc.InvalidApplication('Pending application %r not found '
                    '(already unregistered?)' % (name,))

            return r

        def attach_application(res):
            self.applications[name] = app
            app.factory = self
            app.name = name

            return res

        d.addBoth(cleanup_pending).addCallback(attach_application)

        return d

    def unregisterApplication(self, name):
        """
        Unregisters and removes the named application from this factory. Any
        subsequent connect attempts to the C{name} will be met with an error.

        @return: A L{defer.Deferred} when the process is complete. The result
            will be the application instance that was successfully unregistered.
        """
        try:
            app = self._pendingApplications.pop(name)

            return defer.succeed(app)
        except KeyError:
            pass

        try:
            app = self.applications[name]
        except KeyError:
            raise exc.InvalidApplication('Unknown application %r' % (name,))

        # TODO: run through the attached clients and signal the app shutdown.
        d = defer.maybeDeferred(app.shutdown)

        def cb(res):
            app = self.applications.pop(name)
            app.factory = None
            app.name = None

            return app

        d.addBoth(cb)

        return d

    def buildHandshakeNegotiator(self, protocol):
        """
        Returns a negotiator capable of handling server side handshakes.

        @param protocol: The L{ServerProtocol} requiring handshake negotiations.
        """
        i = handshake.get_implementation(self.protocolVersion)

        return i.ServerNegotiator(protocol, protocol.transport)
