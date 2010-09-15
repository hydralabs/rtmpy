# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Server implementation.
"""

from zope.interface import Interface, Attribute, implements
from twisted.internet import protocol, defer
import pyamf

from rtmpy import util, exc, versions
from rtmpy.protocol.rtmp import message, expose, status
from rtmpy.protocol import rtmp, handshake, version


class IApplication(Interface):
    """
    """

    clients = Attribute("A collection of clients connected to this application.")
    name = Attribute("The name of the application instance.")
    factory = Attribute("The Factory instance that this application is"
        "attached to.")
    streams = Attribute("A collection of streams that this application is "
        "currently publishing")

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

    def onPublish(client, stream):
        """
        """


class Client(object):
    """
    """

    def __init__(self, nc):
        self.nc = nc
        self.application = None


class ServerProtocol(rtmp.RTMPProtocol):
    """
    Server side RTMP protocol implementation
    """

    def startStreaming(self):
        """
        """
        rtmp.RTMPProtocol.startStreaming(self)

        self.connected = False
        self.application = None

    @expose('connect')
    def onConnect(self, args):
        if self.connected:
            return

        def connection_accepted(res):
            """
            Called when the application has accepted the connection
            (in principle)
            """
            oE = args.pop('objectEncoding', self.objectEncoding)

            self.objectEncoding = oE

            f = self.factory

            # begin negotiating bandwidth
            self.sendMessage(message.DownstreamBandwidth(f.downstreamBandwidth))
            self.sendMessage(message.UpstreamBandwidth(f.upstreamBandwidth, 2))

            return res

        def return_success(res):
            self.connected = True
            del self._pendingConnection

            result = status.status('NetConnection.Connect.Success',
                description='Connection succeeded.',
                objectEncoding=self.objectEncoding)

            return rtmp.ExtraResult(result,
                # what are these values?
                {'mode': 1, 'capabilities': 31, 'fmsVer': 'FMS/3,5,1,516'})

        def eb(fail):
            """
            Called when an error occurred when asking the application to
            validate the connection request.
            """
            code = getattr(fail.value, 'code', 'NetConnection.Connect.Failed')
            description = fail.getErrorMessage() or 'Internal Server Error'

            return status.error(code, description)

        def chain_errback(f):
            self._pendingConnection.errback(f)

        self._pendingConnection = defer.Deferred()

        self._pendingConnection.addCallbacks(return_success, eb)

        d = defer.maybeDeferred(self._onConnect, *(args,))

        d.addCallback(connection_accepted)
        d.addErrback(chain_errback)

        # todo: timeout for connection
        return self._pendingConnection

    def _onConnect(self, args):
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

            self.application.acceptConnection(self.client)

        d = defer.maybeDeferred(self.application.onConnect, self.client, **args)

        d.addCallback(cb)

        return d

    def onDownstreamBandwidth(self, interval, timestamp):
        """
        """
        rtmp.RTMPProtocol.onDownstreamBandwidth(self, interval, timestamp)

        if not self.connected:
            self._pendingConnection.callback(None)


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
        self.clients[client.id] = client

    def acceptConnection(self, client):
        """
        """

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

    def clientDisconnected(self, client, reason):
        pass

    def buildClient(self, protocol):
        """
        Create an instance of a subclass of L{Client}. Override this method to
        alter how L{Client} instances are created.

        @param protocol: The L{rtmp.ServerProtocol} instance.
        """
        c = self.client(protocol)

        c.id = util.generateBytes(9, readable=True)

        return c

    def onConnect(self, client, **args):
        """
        Called when a connection request is made to this application. Must
        return a C{bool} (or a L{defer.Deferred} returning a C{bool}) which
        determines the result of the connection request.

        If C{False} is returned (or an exception raised) then the connection is
        rejected. The default is to accept the connection.

        @param client: The client requesting the connection.
        @type client: An instance of L{client_class}.
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


class ServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory.

    Maintains a collection of applications that RTMP peers connect and
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
    fmsVer = versions.FMS_MIN_H264

    def __init__(self, applications=None):
        self.applications = {}
        self._pendingApplications = {}

        if applications:
            for name, app in applications.items():
                self.registerApplication(name, app)

    def buildHandshakeNegotiator(self, protocol):
        """
        Returns a negotiator capable of handling server side handshakes.

        @param protocol: The L{ServerProtocol} requiring handshake negotiations.
        """
        i = handshake.get_implementation(self.protocolVersion)

        return i.ServerNegotiator(protocol, protocol.transport)

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
