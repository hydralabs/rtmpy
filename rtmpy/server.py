# -*- test-case-name: rtmpy.tests.test_server -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Server implementation.

@since: 0.1.0
"""

from zope.interface import Interface, Attribute, implements
from twisted.internet import protocol, defer, reactor
import pyamf

from rtmpy import rtmp, util
from rtmpy.rtmp import handshake, scheduler, stream, event, status


class IApplication(Interface):
    """
    """

    clients = Attribute("A list of all clients connected to the application.")
    name = Attribute("The name of the application instance.")

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
        Called when the client has been accepted by this application.
        """

    def disconnect(client):
        """
        Disconnects a client from the application. Returns a deferred that is
        called when the disconnection was successful.
        """


class Client(object):
    """
    """

    def __init__(self, protocol):
        self.protocol = protocol
        self.application = None

        self.pendingCalls = []

    def call(self, name, *args):
        """
        """
        d = defer.Deferred()

        if self.application is None:
            self.pendingCalls.append((name, args, d))

            return d

        s = self.protocol.getStream(0)
        x = s.writeEvent(event.Invoke(name, 0, *args), channelId=3)

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


class Application(object):
    """
    """

    implements(IApplication)

    client_class = Client

    def __init__(self):
        self.clients = []
        self.streams = {}

    def startup(self):
        """
        Called when the application is starting up.
        """

    def shutdown(self):
        """
        Called when the application is closed.
        """

    def acceptConnection(self, client):
        """
        Called when this application has accepted the client connection.
        """
        client.id = util.generateBytes(9)

        self.clients.append(client)

    def disconnect(self, client):
        """
        Removes the C{client} from this application.
        """
        try:
            self.clients.remove(client)
        except ValueError:
            pass

    def buildClient(self, protocol):
        """
        """
        return self.client_class(protocol)

    def onConnect(self, client, **kwargs):
        """
        Called when a connection request is made to this application. Must
        return a C{bool} (or a L{defer.Deferred} returning a C{bool}) which
        determines the result of the connection request.

        If C{True} is returned then the connection is accepted. If C{False} is
        returned then the connection is rejected

        @param client: The client requesting the connection.
        @type client: An instance of L{client_class}.
        @param kwargs: The arguments supplied as part of the connection
            request.
        @type kwargs: C{dict}
        """
        return True

    def getStream(self, name):
        """
        """
        try:
            return self.streams[name]
        except KeyError:
            self.streams[name] = object()

        return self.streams[name]


class ApplicationContext(object):
    """
    """

    def __init__(self, factory, application):
        self.factory = factory
        self.application = application


class ServerProtocol(rtmp.BaseProtocol):
    """
    A basic RTMP protocol that will act like a server.
    """

    def buildHandshakeNegotiator(self):
        """
        Generate a server handshake negotiator.

        @rtype: L{handshake.ServerNegotiator}
        """
        return handshake.ServerNegotiator(self)

    def connectionMade(self):
        """
        Called when a connection is made to the RTMP server. Will begin
        handshake negotiations.
        """
        rtmp.BaseProtocol.connectionMade(self)

        self.handshaker.start(version=0)

    def handshakeSuccess(self):
        """
        Called when the handshake has been successfully negotiated. If there
        is any data in the negotiator buffer it will be re-inserted into the
        main RTMP stream (as any data after the handshake must be RTMP).
        """
        b = self.handshaker.buffer

        rtmp.BaseProtocol.handshakeSuccess(self)

        self.encoder.registerScheduler(scheduler.LoopingChannelScheduler())

        s = stream.ServerControlStream(self)

        self.registerStream(0, s)
        self.client = None
        self.application = None

        if len(b) > 0:
            self.dataReceived(b)

    def connectionLost(self, reason):
        """
        """
        rtmp.BaseProtocol.connectionLost(self, reason)

        if hasattr(self, 'client') and hasattr(self, 'application'):
            if self.client and self.application:
                self.application.disconnect(self.client)

    def onConnect(self, args):
        """
        Called when a 'connect' packet is received from the client.
        """
        try:
            appName = args['app']
        except KeyError:
            return None, status.status(
                code='NetConnection.Connect.Failed',
                description='Bad connect packet (missing `app` key)'
            )

        self.application = self.factory.getApplication(appName)

        if self.application is None:
            return None, status.error(
                code='NetConnection.Connect.Failed',
                description='Unknown application'
            )

        self.client = self.application.buildClient(self)

        self.pendingConnection = defer.Deferred()

        def cb(res):
            if res is False:
                self.pendingConnection.callback((None, status.error(
                    code='NetConnection.Connect.Rejected',
                )))

                return

            self.application.acceptConnection(self.client)

            s = self.getStream(0)

            s.writeEvent(event.DownstreamBandwidth(2500000L), channelId=2)
            s.writeEvent(event.UpstreamBandwidth(2500000L, 2), channelId=2)

        d = defer.maybeDeferred(self.application.onConnect, self.client, **args)

        d.addCallback(cb)

        return self.pendingConnection

    def createStream(self):
        streamId = self.getNextAvailableStreamId()

        self.registerStream(streamId, stream.Stream(self))

        print 'createStream', streamId
        return None, streamId

    def deleteStream(self, streamId):
        """
        """
        try:
            del self.streams[streamId]
        except:
            pass

    def onDownstreamBandwidth(self, bandwidth):
        self.clientBandwidth = bandwidth

        if hasattr(self, 'pendingConnection'):
            s = self.getStream(0)

            s.writeEvent(event.ControlEvent(0, 0), channelId=2)

            x = {'fmsVer': u'FMS/3,5,1,516', 'capabilities': 31, 'mode': 1}

            def y(res):
                self.client.registerApplication(self.application)

                return res

            self.pendingConnection.addCallback(y)

            self.pendingConnection.callback((x, status.status(
                code=u'NetConnection.Connect.Success',
                description=u'Connection succeeded.',
                objectEncoding=0
            )))

            del self.pendingConnection


class ServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory.
    """

    protocol = ServerProtocol

    def __init__(self, applications={}):
        self.applications = applications
        self.applicationContext = {}

        for name, app in self.applications.iteritems():
            self.registerApplication(name, app)

    def getApplication(self, name):
        """
        Returns the application mounted at C{name}, if any.
        """
        return self.applications.get(name, None)

    def registerApplication(self, name, app):
        """
        """
        self.applications[name] = app

        app.name = name

        d = defer.maybeDeferred(app.startup)

        def eb(f):
            self.unregisterApplication(app)

            return f

        def cb(res):
            self.applicationContext[app] = ApplicationContext(self, app)
            app.context = self.applicationContext[app]
            app.factory = self

            return res

        d.addErrback(eb).addCallback(cb)

        return d

    def unregisterApplication(self, nameOrApp):
        """
        """
        name = None

        if IApplication.implementedBy(nameOrApp):
            name = app.name
        else:
            name = nameOrApp

        app = self.applications[name]

        # if the app exists in the applicationContext then it has successfully
        # completed its `startup` and is considered active.
        if app in self.applicationContext:
            d = defer.maybeDeferred(app.shutdown)
        else:
            d = defer.succeed()

        def cb(res):
            if app in self.applicationContext:
                del self.applicationContext[app]

            del self.applications[name]

            return res

        d.addBoth(cb)

        return d
