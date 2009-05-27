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


class ServerControlStream(stream.BaseStream):
    """
    """

    def _fatal(self, f):
        """
        If we ever get here then a pathological error occurred and the only
        thing left to do is to log the error and kill the connection.

        Only to be used as part of a deferred call/errback chain.
        """
        self.protocol.logAndDisconnect(f)

    def onInvoke(self, invoke):
        """
        """
        d = None

        def cb(res):
            if not isinstance(res, (tuple, list)):
                res = (None, res)

            s = res[1]

            if isinstance(s, status.Status):
                if s.level == 'error':
                    return event.Invoke('_error', invoke.id, *res)

            return event.Invoke('_result', invoke.id, *res)

        if invoke.name == u'connect':
            def eb(f):
                # TODO: log the error
                print f
                return status.error(
                    code='NetConnection.Connect.Failed',
                    description='Internal Server Error'
                )

            def check_error(res):
                if not isinstance(res, event.Invoke):
                    return res

                if res.name == '_error':
                    self.writeEvent(res, channelId=2)
                    self.writeEvent(event.Invoke('close', 0, None), channelId=2)

                    return

                return res

            d = defer.maybeDeferred(self.protocol.onConnect, *invoke.argv)
            d.addErrback(eb).addCallback(cb).addCallback(check_error)
        elif invoke.name == u'createStream':
            d = defer.maybeDeferred(self.protocol.createStream)

            d.addCallback(cb)
        elif invoke.name == u'deleteStream':
            d = defer.maybeDeferred(self.protocol.removeStream, *invoke.argv[1:])

            d.addCallback(cb).addCallback(lambda _: None)
        else:
            def eb(f):
                # TODO: log the error
                print f
                return status.error(
                    code='NetConnection.Call.Failed',
                    description='Internal Server Error'
                )

            kls = self.protocol.client.__class__

            if not hasattr(kls, invoke.name):
                return status.error(
                    code='NetConnection.Call.Failed',
                    description="Unknown method '%s'" % (invoke.name,)
                )

            method = getattr(self.protocol.client, invoke.name)

            d = defer.maybeDeferred(method, *invoke.argv[1:])

            d.addErrback(eb).addCallback(cb)

        return d.addErrback(self._fatal)

    def onDownstreamBandwidth(self, bandwidth):
        """
        """
        self.protocol.onDownstreamBandwidth(bandwidth)

    def onFrameSize(self, size):
        self.protocol.decoder.setFrameSize(size)


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

    def acceptConnection(self, client):
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
            s = self.streams[name] = stream.SubscriberStream()
            s.application = self

        return self.streams[name]

    def onPublish(self, stream):
        """
        """


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
        self.client = None
        self.application = None
        self.pendingConnection = None

    def handshakeSuccess(self):
        """
        Called when the handshake has been successfully negotiated. If there
        is any data in the negotiator buffer it will be re-inserted into the
        main RTMP stream (as any data after the handshake must be RTMP).
        """
        b = self.handshaker.buffer

        rtmp.BaseProtocol.handshakeSuccess(self)

        s = ServerControlStream(self)

        self.registerStream(0, s)

        self.encoder.registerScheduler(scheduler.LoopingChannelScheduler())

        if len(b) > 0:
            self.dataReceived(b)

    def connectionLost(self, reason):
        """
        The connection to the client has been lost.
        """
        rtmp.BaseProtocol.connectionLost(self, reason)

        if self.client and self.application:
            self.application.disconnect(self.client)

        if self.pendingConnection:
            self.pendingConnection.errback(reason)

            self.pendingConnection = None

    def onConnect(self, args):
        """
        Called when a 'connect' packet is received from the client.
        """
        if self.application:
            # This protocol has already successfully completed a connection
            # request.

            # TODO, kill the connection
            return status.status(
                code='NetConnection.Connect.Closed',
                description='Already connected.'
            )

        try:
            appName = args['app']
        except KeyError:
            return status.status(
                code='NetConnection.Connect.Failed',
                description='Bad connect packet (missing `app` key)'
            )

        self.application = self.factory.getApplication(appName)

        if self.application is None:
            return status.error(
                code='NetConnection.Connect.InvalidApp',
                description='Unknown application \'%s\'' % (appName,)
            )

        self.client = self.application.buildClient(self)
        self.pendingConnection = defer.Deferred()

        def cb(res):
            self.objectEncoding = args.get('objectEncoding', pyamf.AMF0)

            if res is False:
                self.pendingConnection = None

                return status.error(
                    code='NetConnection.Connect.Rejected',
                    description='Authorization is required'
                )

            self.application.acceptConnection(self.client)

            s = self.getStream(0)

            s.writeEvent(event.DownstreamBandwidth(self.factory.downstreamBandwidth), channelId=2)
            s.writeEvent(event.UpstreamBandwidth(self.factory.upstreamBandwidth, 2), channelId=2)

            # clear the stream
            d = s.writeEvent(event.ControlEvent(0, 0), channelId=2)

            def sendStatus(res):
                x = {'fmsVer': self.factory.fmsVer, 'capabilities': 31}

                def y(res):
                    self.client.registerApplication(self.application)

                    return res

                self.pendingConnection.addCallback(y)

                self.pendingConnection.callback((x, status.status(
                    code=u'NetConnection.Connect.Success',
                    description=u'Connection succeeded.',
                    objectEncoding=0
                )))

                self.pendingConnection = None

            d.addCallback(sendStatus)

            # TODO: A timeout for the pendingConnection
            return self.pendingConnection

        def eb(f):
            print 'failed app.onConnect', f
            return status.status(
                code='NetConnection.Connect.Failed',
                description='Internal Server Error'
            )

        d = defer.maybeDeferred(self.application.onConnect, self.client, **args)

        d.addCallback(cb)

        if d.called:
            return d

        return self.pendingConnection

    def createStream(self):
        """
        """
        streamId = self.getNextAvailableStreamId()

        self.registerStream(streamId, stream.Stream(self))

        return streamId

    def onDownstreamBandwidth(self, bandwidth):
        self.client.upstreamBandwidth = bandwidth


class ServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory.
    """

    protocol = ServerProtocol

    upstreamBandwidth = 2500000L
    downstreamBandwidth = 2500000L
    fmsVer = u'FMS/3,5,1,516'

    def __init__(self, applications={}):
        self.applications = {}
        self._pendingApplications = {}

        for name, app in applications.iteritems():
            self.registerApplication(name, app)

    def getApplication(self, name):
        """
        Returns the application mounted at C{name}, if any.
        """
        return self.applications.get(name, None)

    def registerApplication(self, name, app):
        """
        """
        self._pendingApplications[name] = app

        d = defer.maybeDeferred(app.startup)

        def eb(f):
            del self._pendingApplications[name]

            return f

        def cb(res):
            self.applications[name] = app
            app.factory = self
            app.name = name

            return res

        d.addBoth(eb).addCallback(cb)

        return d

    def unregisterApplication(self, nameOrApp):
        """
        """
        name = nameOrApp

        if IApplication.implementedBy(nameOrApp):
            name = app.name

        app = self.applications[name]

        d = defer.maybeDeferred(app.shutdown)

        def cb(res):
            del self.applications[name]
            app.factory = None
            app.name = None

            return res

        d.addBoth(cb)

        return d
