# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
Server implementation.
"""
import urlparse

from zope.interface import Interface, Attribute, implements
from twisted.internet import protocol, defer
from twisted.python import failure, log
import pyamf

from rtmpy import util, exc, versions
from rtmpy import message, rpc, status, core
from rtmpy.protocol import rtmp, handshake, version
from rtmpy.status import codes


class IApplication(Interface):
    """
    An application provides business logic for connected clients and streams.
    """

    clients = Attribute("A list of clients connected to this application.")
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

    def buildClient(protocol, params, *args):
        """
        Returns a client object linked to the protocol object.

        @param params: The connection parameters sent from the client, this
            includes items such as the connection url, and user agent
        @type params: C{dict}
        @param args: The client supplied arguments to NetConnection.connect()
        """

    # events

    def onAppStart():
        """
        Called when the application has been fully loaded by the server and is
        ready to start accepting connections.
        """

    def onAppStop(reason):
        """
        @todo - implement this feature
        """

    def onConnect(client, *args):
        """
        Called when the peer connects to an application (NetConnection.connect).

        Return a C{True}/C{False} value to accept/reject the connection request.
        Alternatively return a L{defer.Deferred} to put the request in a pending
        state.

        If C{True} is (eventually) returned, L{acceptConnection} is called,
        otherwise L{rejectConnection}.

        @param client: The client object built by L{buildClient}
        @param args: The client supplied arguments to NetConnection.connect()
        """

    def onConnectAccept(client, *args):
        """
        Called when the peer has been successfully connected to this application.

        @param client: The client object built by L{buildClient}
        @param args: The client supplied arguments to NetConnection.connect()
        """

    def onConnectReject(client, reason, *args):
        """
        Called when the application has rejected the peers connection attempt.

        @param client: The client object built by L{buildClient}
        @param args: The client supplied arguments to NetConnection.connect()
        """

    def onDisconnect(client):
        """
        Called when a client has been disconnected from the application.
        """

    def onPublish(client, stream):
        """
        Called when the stream is publishing a video/audio stream.

        @param client: The client linked to the stream.
        @param stream: The L{NetStream} making the publish request.
        """


class IPublishingStream(Interface):
    """
    The name should be enough :)
    """

    def started(self):
        """
        Publishing has now started (or resumed).
        """

    def stopped(self):
        """
        Publishing has been stopped/paused.

        @todo: Distinguish between a paused/starved stream and a stream that has
            gone away.
        """

    def videoDataReceived(data, timestamp):
        """
        A video packet has been received from the publishing stream.

        @param data: The raw video data.
        @type data: C{str}
        @param timestamp: The timestamp at which this data was received.
        """

    def audioDataReceived(data, timestamp):
        """
        An audio packet has been received from the publishing stream.

        @param data: The raw audio data.
        @type data: C{str}
        @param timestamp: The timestamp at which this data was received.
        """

    def onMetaData(data):
        """
        The meta data for the a/v stream has been updated.
        """


class Client(object):
    """
    A very basic client object that relates an application to a connected peer.
    Quite what to do with it right now is anyone's guess ..

    @param nc: The L{ServerProtocol} instance.
    @param id: The application provided unique id for this client.
    """

    def __init__(self, nc):
        self.nc = nc
        self.id = None

    def call(self, name, *args, **kwargs):
        return self.nc.call(name, *args, **kwargs)



class NetStream(core.NetStream):
    """
    A server side NetStream. Knows nothing of L{IApplication}s but interfaces
    directly with the L{ServerProtocol} (which does). A NetStream is dumb and
    defers all logic to the L{NetConnection<ServerProtocol>}.

    @param state: The state of the NetStream. Right now the only valid values
        are C{None} and C{'publishing'}.
    @param name: The name of the published stream. Use this to look up the
        stream in the application.
    @param publisher: When published, this is set to the instance that will
        receive the audio/video/meta data events from the peer. See
        L{StreamPublisher} for now.
    @type publisher: L{IPublishingStream}
    """

    def __init__(self, nc, streamId):
        core.NetStream.__init__(self, nc, streamId)

        self.state = None
        self.name = None
        self.publisher = None

    def publishingStarted(self, publisher, name):
        """
        Called when this NetStream has started publishing data from the
        connected peer.
        """
        self.publisher = publisher
        self.name = name
        self.state = 'publishing'

    @rpc.expose
    def receiveAudio(self, audio):
        """
        """

    @rpc.expose
    def receiveVideo(self, video):
        """
        """

    @rpc.expose
    def publish(self, name, type_='live'):
        """
        Called by the peer to start pushing video/audio data.

        @param name: The name of the stream to publish.
        @param type_: The type of stream to be published.
        @see: possible values for U{type_<http://www.adobe.com/livedocs/
            flashmediaserver/3.0/hpdocs/00000349.html>}
        """
        d = defer.maybeDeferred(self.nc.publishStream, self, name, type_)

        def send_status(result):
            s = None

            if isinstance(result, failure.Failure):
                code = getattr(result.value, 'code', 'NetConnection.Call.Failed')
                description = util.getFailureMessage(result) or 'Internal Server Error'

                s = status.error(code, description)
            else:
                s = status.status('NetStream.Publish.Start',
                    description='%s is now published.' % (name,),
                    clientid=self.client.id)

            self.sendStatus(s)

            return result

        d.addBoth(send_status)

        return d

    @rpc.expose
    def closeStream(self):
        """
        Called when the stream is closing.
        """
        d = defer.succeed(None)

        if self.state == 'publishing':
            d = defer.maybeDeferred(self.nc.unpublishStream, self, self.name)

            def send_status(res):
                self.sendStatus(status.status('NetStream.Unpublish.Success',
                    description='%s is now unpublished.' % (self.name,),
                    clientid=self.nc.client.id))

                return res

            d.addBoth(send_status)

        def clear_state(res):
            self.state = None

            return res

        d.addBoth(clear_state)

        return d

    def unpublish(self):
        """
        Called when the producer stream has gone away. Perform clean up here.
        """
        # todo inform the nc that the stream went away
        self.sendStatus('NetStream.Play.UnpublishNotify')

    def onVideoData(self, data, timestamp):
        """
        Called when a video packet has been received from the peer.

        Pushes the message on to the publisher.

        @param data: The raw video data.
        @type data: C{str}
        @param timestamp: The timestamp at which this message was received.
        """
        if self.publisher:
            self.publisher.videoDataReceived(data, timestamp)

    def onAudioData(self, data, timestamp):
        """
        Called when an audio packet has been received from the peer.

        Pushes the message on to the publisher.

        @param data: The raw audio data.
        @type data: C{str}
        @param timestamp: The timestamp at which this message was received.
        """
        if self.publisher:
            self.publisher.audioDataReceived(data, timestamp)

    @rpc.expose('@setDataFrame')
    def setDataFrame(self, name, meta):
        """
        Called by the peer to set the 'data frame'? Not quite sure what this is
        all about but it contains any meta data updates for the a/v.

        We hand this responsibility to the publisher.

        @param name: This appears to be the name of the event to call. It is
            always 'onMetaData'.
        @param meta: The updated meta data for the stream.
        """
        func = getattr(self.publisher, name, None)

        if func and name == 'onMetaData':
            func(meta)


    @rpc.expose('@clearDataFrame')
    def clearDataFrame(self, name):
        """
        Called by the peer to clear the metadata from a live stream.

        We hand this responsibility to the publisher.

        @param name: This appears to be the name of the event to call. It is
            always 'onMetaData'.
        """
        func = getattr(self.publisher, name, None)

        if func and name == 'onMetaData':
            func(dict())


    @rpc.expose
    def play(self, name, *args):
        d = defer.maybeDeferred(self.nc.playStream, name, self, *args)

        def cb(res):
            """
            The stream has started playing
            """
            self._audioChannel = self.nc.getStreamingChannel(self)
            self._audioChannel.setType(message.AUDIO_DATA)

            self._videoChannel = self.nc.getStreamingChannel(self)
            self._videoChannel.setType(message.VIDEO_DATA)

            self.state = 'playing'

            # wtf
            self.sendMessage(message.ControlMessage(4, 1))
            self.sendMessage(message.ControlMessage(0, 1))

            self.sendStatus('NetStream.Play.Reset',
                description='Playing and resetting %s' % (name,),
                clientid=self.nc.clientId)

            self.sendStatus('NetStream.Play.Start',
                description='Started playing %s' % (name,),
                clientid=self.nc.clientId)

            self.nc.call('onStatus', {'code': 'NetStream.Data.Start'})

            return res

        def eb(fail):
            code = getattr(fail.value, 'code', 'NetStream.Play.Failed')
            description = util.getFailureMessage(fail) or 'Internal Server Error'

            self.sendStatus(status.error(code, description))

            return fail

        d.addErrback(eb)
        d.addCallback(cb)

        return d

    def onMetaData(self, data):
        """
        """
        self.call('onMetaData', data)

    def videoDataReceived(self, data, timestamp):
        self._videoChannel.sendData(data, timestamp)

    def audioDataReceived(self, data, timestamp):
        self._audioChannel.sendData(data, timestamp)



class NetConnection(core.NetConnection):
    """
    Server side NetConnection implementation.
    """

    objectEncoding = pyamf.AMF0

    def __init__(self, protocol):
        core.NetConnection.__init__(self, protocol)

        self.connected = False
        self.application = None
        self.clientId = None


    def buildStream(self, streamId):
        """
        """
        return NetStream(self, streamId)


    def publishStream(self, stream, streamName, type_):
        """
        Called when a L{NetStream} wants to publish a stream through this
        C{NetConnection}.

        @param stream: The L{NetStream} instance requesting the publication.
        @param streamName: The name of the stream to be published.
        @param type_: Not quite sure of the significance of this yet - valid
            values appear to be 'live', 'append', 'record'.
        """
        streamName = util.ParamedString(streamName)

        if not self.connected:
            raise exc.ConnectError('Cannot publish stream - not connected')

        d = defer.maybeDeferred(self.application.publishStream,
            self.client, stream, streamName, type_)

        def cb(publisher):
            """
            Called when the application has published the stream.

            @param publisher: L{StreamPublisher}
            """
            stream.publishingStarted(publisher, streamName)
            publisher.start()
            self.application.onPublish(self.client, stream)

            return publisher

        d.addCallback(cb)

        return d

    def unpublishStream(self, stream, streamName):
        """
        The C{stream} is unpublishing itself.

        @param stream: The stream that has unpublished itself.
        @type stream: L{NetStream}
        @param streamName: The name of the stream being unpublished. Not used.
        """
        self.application.unpublishStream(streamName, stream)

        try:
            self.application.onUnpublish(self.client, stream)
        except Exception:
            log.err()


    @rpc.expose
    def releaseStream(self, name):
        """
        Called when the stream is released. Not sure about this one.
        """


    def closeStream(self):
        """
        Called when the stream is asked to close itself.

        Since this class is considered the B{NetConnection} equivalent, we
        propagate the event to the attached application (if one exists)
        """
        if self.application:
            self.application._disconnect(self.client)


    def playStream(self, name, subscriber, *args):
        """
        """
        d = defer.Deferred()

        def whenPublished(publisher):
            publisher.addSubscriber(subscriber)

            return publisher

        self.application.whenPublished(name, d.callback)

        d.addCallback(whenPublished)

        return d


    def callExposedMethod(self, name, *args):
        """
        Used to match a callable based on the supplied name when a notify or
        invoke is encountered. Returns C{None} if not found.

        If no match is found from the superclass, the C{client} and then the
        C{application} are checked in that order.

        All methods on a client/application is considered B{public} and
        accessible by the peer.

        @see: L{rtmp.RTMPProtocol.getInvokableTarget}
        """
        # all client methods are publicly accessible
        client = getattr(self, 'client', None)

        if client:
            target = util.get_callable_target(client, name)

            if target:
                return defer.maybeDeferred(target, *args)

        return core.NetConnection.callExposedMethod(self, name, *args)


    @rpc.expose('connect')
    def onConnect(self, params, *args):
        """
        Connects this protocol instance to an application. The application has
        the power to reject the connection (see L{Application.rejectConnection})

        Will return a L{defer.Deferred} that will contain the result of the
        connection request. The return is paused until the peer has sent its
        bandwidth negotiation packets. See L{onDownstreamBandwidth}.

        @param params: The connection parameters sent from the client, this
            includes items such as the connection url, and user agent
        @type params: C{dict}
        @param args: The client supplied arguments to NetConnection.connect()
        """
        def connection_accepted(res):
            """
            Called when the application has accepted the connection
            (in principle)
            """
            oe = params.pop('objectEncoding', self.objectEncoding)

            self.objectEncoding = oe

            f = self.protocol.factory

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

            self.sendMessage(message.ControlMessage(0, 0))

            return rpc.CommandResult(result,
                # what are these values?
                {'mode': 1, 'capabilities': 31, 'fmsVer': 'FMS/3,5,1,516'})

        def lose_connection():
            self.protocol.transport.loseConnection()


        @rpc.after(lose_connection)
        def eb(fail):
            """
            Called when an error occurred when asking the application to
            validate the connection request.
            """
            if self.application and self.client:
                self.application.onConnectReject(self.client, fail, *args)

            return status.fromFailure(fail, codes.NC_CONNECT_FAILED,
                objectEncoding=self.objectEncoding)


        def chain_errback(f):
            self._pendingConnection.errback(f)

        self._pendingConnection = defer.Deferred()

        self._pendingConnection.addCallbacks(return_success, eb)

        d = defer.maybeDeferred(self._onConnect, params, *args)

        d.addCallback(connection_accepted)
        d.addErrback(chain_errback)

        # todo: timeout for connection
        return self._pendingConnection

    def _onConnect(self, params, *args):
        """
        The business logic of connecting to the application.

        @param params: The connection parameters sent from the client, this
            includes items such as the connection url, and user agent
        @type params: C{dict}

        @param args: arguments from RTMP connect packet
        """
        if self.application:
            # This protocol has already successfully completed a connection
            # request.
            raise exc.ConnectFailed('Already connected.')

        self.application = self.protocol.factory.getApplicationWithDefault(params, *args)

        self.client = self.application.buildClient(self, params, *args)

        def cb(res):
            """
            Called with the result of the connection attempt, either C{True} or
            C{False}.
            """
            if res is False:
                raise exc.ConnectRejected('Authorization is required')

            self.application.acceptConnection(self.client)
            self.application.onConnectAccept(self.client, *args)

        d = defer.maybeDeferred(self.application.onConnect, self.client, *args)

        d.addCallback(cb)

        return d

    def sendMessage(self, msg, stream=None, whenDone=None):
        """
        """
        self.protocol.sendMessage(msg, stream or self, whenDone=whenDone)


    def getStreamingChannel(self, stream):
        return self.protocol.getStreamingChannel(stream)



class ServerProtocol(rtmp.RTMPProtocol):
    """
    Server side RTMP protocol implementation. Handles connection and stream
    management. Provides a proxy between streams and the associated application.
    """

    netconnection = NetConnection


    def buildStreamManager(self):
        return self.nc

    def versionSuccess(self):
        self.transport.write('\x03')

        rtmp.RTMPProtocol.versionSuccess(self)

    def startStreaming(self):
        """
        """
        self.nc = self.netconnection(self)

        rtmp.RTMPProtocol.startStreaming(self)


    def onConnect(self, params, *args):
        return self.nc.onConnect(params, *args)

    def onDownstreamBandwidth(self, interval, timestamp):
        """
        """
        rtmp.RTMPProtocol.onDownstreamBandwidth(self, interval, timestamp)

        if hasattr(self.nc, '_pendingConnection'):
            if not self.nc._pendingConnection.called:
                self.nc._pendingConnection.callback(None)


    def closeStream(self):
        """
        Called when the stream is asked to close itself.
        """
        self.nc.closeStream()


    def onInvoke(self,name, callId, args, timestamp):
        """
        """
        self.nc.onInvoke(name, callId, args, timestamp)


    def onNotify(self, name, args, timestamp):
        """
        """
        self.nc.onNotify(name, args, timestamp)


    def onControlMessage(self, *args):
        """
        """


    def onBytesRead(self, *args):
        """
        """



class StreamPublisher(object):
    """
    Linked to a L{NetStream} when it makes a publish request. Manages a list of
    subscribers to the stream and propagates the events when the stream produces
    them.

    @ivar stream: The publishing L{NetStream}
    @ivar client: The linked L{Client} object. Not used right now.
    @ivar subscribers: A list of subscribers that are listening to the stream.
    @ivar
    """

    implements(IPublishingStream)

    def __init__(self, stream, client):
        self.stream = stream
        self.client = client

        self.subscribers = {}
        self.meta = {}
        self.timestamp = self.baseTimestamp = 0

    def _updateTimestamp(self, timestamp):
        """
        """
        if timestamp == 0:
            self.baseTimestamp = self.timestamp

            return self.timestamp

        self.timestamp = self.baseTimestamp + timestamp

        return self.timestamp

    def addSubscriber(self, subscriber):
        """
        Adds a subscriber to this publisher.
        """
        self.subscribers[subscriber] = {
            'timestamp': self.timestamp
        }

        if self.meta:
            subscriber.onMetaData(self.meta)

    def removeSubscriber(self, subscriber):
        """
        Removes the subscriber from this publisher.
        """
        self.subscribers.pop(subscriber)

    # events called by the stream

    def videoDataReceived(self, data, timestamp):
        """
        A video packet has been received from the publishing stream.

        @param data: The raw video data.
        @type data: C{str}
        @param timestamp: The timestamp at which this data was received.
        """
        timestamp = self._updateTimestamp(timestamp)

        to_remove = []

        for subscriber, context in self.subscribers.iteritems():
            relTimestamp = timestamp - context['timestamp']

            try:
                subscriber.videoDataReceived(data, relTimestamp)
            except:
                log.err()
                to_remove.append(subscriber)

        if to_remove:
            for subscriber in to_remove:
                self.removeSubscriber(subscriber)

    def audioDataReceived(self, data, timestamp):
        """
        An audio packet has been received from the publishing stream.

        @param data: The raw audio data.
        @type data: C{str}
        @param timestamp: The timestamp at which this data was received.
        """
        timestamp = self._updateTimestamp(timestamp)
        to_remove = []

        for subscriber, context in self.subscribers.iteritems():
            try:
                subscriber.audioDataReceived(data, timestamp - context['timestamp'])
            except:
                log.err()
                to_remove.append(subscriber)

        if to_remove:
            for subscriber in to_remove:
                self.removeSubscriber(subscriber)

    def onMetaData(self, data):
        """
        The meta data for the a/v stream has been updated.
        """
        self.meta.update(data)

        for a in self.subscribers:
            a.onMetaData(data)

    def start(self):
        pass

    def stop(self):
        pass

    def unpublish(self):
        for a in self.subscribers:
            a.unpublish()

        self.subscribers = {}


class Application(object):
    """
    The business logic behind
    """

    implements(IApplication)

    client = Client

    def __init__(self):
        self.clients = {}
        self.streams = {}
        self._streamingClients = {}
        self._pendingPublishedCallbacks = {}


    def startup(self):
        """
        Called when the application is starting up.
        """


    def shutdown(self):
        """
        Called when the application is closed.
        """


    def getStreamByName(self, name):
        """
        """
        return self.streams[name]


    def acceptConnection(self, client):
        """
        Called when this application has accepted the client connection.
        """
        self.clients[client.id] = client

    def disconnect(self, client):
        """
        Disconnects the client from the server.
        """
        self._disconnect(client)

        client.nc.protocol.transport.loseConnection()


    def _disconnect(self, client):
        """
        Removes the C{client} from this application.
        """
        publisher = self._streamingClients.pop(client, None)

        if publisher:
            name = publisher.stream.name

            try:
                self.unpublishStream(publisher, name)
            except exc.BadNameError:
                pass
            except:
                log.err()

            self.streams.pop(name, None)

        c = self.clients.pop(client.id, None)

        if c is None:
            return

        try:
            self.onDisconnect(client)
        except Exception:
            log.err()


    def buildClient(self, protocol, params, *args):
        """
        Create an instance of a subclass of L{Client}. Override this method to
        alter how L{Client} instances are created.

        @param protocol: The L{rtmp.ServerProtocol} instance.
        @param params: The connection parameters sent from the client, this
            includes items such as the connection url, and user agent
        @type params: C{dict}
        @param args: The client supplied arguments to NetConnection.connect()
        """
        c = self.client(protocol)
        c.id = util.generateBytes(9, readable=True)

        # Inject properties into the client object
        # TODO: Evaluate if these should be defined with @property in the
        #  Client class itself.
        c.application = self

        try:
            c.ip = c.nc.transport.getPeer().host
        except AttributeError:
            c.ip = None

        tcUrl = params.get('tcUrl', '')
        c.protocol = urlparse.urlparse(tcUrl)[0]
        if c.protocol == '':
            c.protocol = None

        c.pageUrl = params.get('pageUrl', None)
        c.uri = params.get('tcUrl', None)
        c.agent = params.get('flashVer', None)

        return c


    def whenPublished(self, name, cb):
        """
        Will call C{cb} when a stream has been published under C{name}

        C{cb} will be called with one argument, the stream object itself.
        """
        if not callable(cb):
            raise TypeError('cb must be callable for whenPublished')

        try:
            publisher = self.streams[name]
        except KeyError:
            cbs = self._pendingPublishedCallbacks.setdefault(name, [])

            cbs.append(cb)

            return

        try:
            cb(publisher)
        except:
            log.err()


    def _runCallbacksForPublishedStream(self, name, stream):
        """
        Iterates over the list of callables to be executed when a stream named
        C{name} is successfully published.
        """
        try:
            cbs = self._pendingPublishedCallbacks[name]
        except KeyError:
            return

        for cb in cbs:
            try:
                cb(stream)
            except:
                log.err()

        del self._pendingPublishedCallbacks[name]


    def publishStream(self, client, requestor, name, type_='live'):
        """
        The C{stream} is requesting to publish an audio/video stream under the
        name C{name}. Reject the publish request by raising an exception.

        @param client: The L{Client} requesting the publishing the stream.
        @param stream: The L{NetStream} that will receive the a/v data.
        @param name: The name of the stream that will be published.
        @param type_: Ignored for now.
        """
        stream = self.streams.get(name, None)

        if stream is None:
            # brand new publish
            stream = self.streams[name] = StreamPublisher(requestor, client)
            self._streamingClients[client] = stream

        if client.id != stream.client.id:
            raise exc.BadNameError("'%s' is already used" % (name,))

        self._runCallbacksForPublishedStream(name, stream)

        return stream


    def unpublishStream(self, name, stream):
        try:
            source = self.streams[name]
        except KeyError:
            raise exc.BadNameError("Unknown stream '%s'" % (name,))

        if source.client.id != stream.client.id:
            raise exc.BadNameError('Unable to unpublish stream')

        try:
            source.unpublish()
        except:
            log.err()

        del self.streams[name]


    def addSubscriber(self, stream, subscriber):
        """
        Adds a subscriber to a stream.

        @type stream: L{NetStream}
        @type subscriber: L{IPublishingStream}
        """
        self.streams[stream.name].addSubscriber(subscriber)

    def removeSubscriber(self, stream, subscriber):
        """
        Removes a subscriber from a stream.

        @type stream: L{NetStream}
        @type subscriber: L{IPublishingStream}
        """
        self.streams[stream.name].removeSubscriber(subscriber)

    def onAppStart(self):
        """
        Called when the application is ready to connect clients
        """

    def onConnect(self, client, *args):
        """
        Called when a connection request is made to this application. Must
        return a C{bool} (or a L{defer.Deferred} returning a C{bool}) which
        determines the result of the connection request.

        If C{False} is returned (or an exception raised) then the connection is
        rejected. The default is to accept the connection.

        @param client: The client requesting the connection.
        @type client: An instance of L{client_class}.
        """

    def onConnectAccept(self, client, *args):
        """
        Called when the peer has successfully been connected to this
        application.

        @param client: The L{Client} object representing the peer.
        @param kwargs: A dict of name/value pairs that were sent with the
            connect request.
        """

    def onConnectReject(self, client, reason, *args):
        """
        Called when a connection request has been rejected.

        @param client: The L{Client} object representing the peer.
        @param reason: A L{failure.Failure} object representing the reason why
            the client was rejected.
        @param args: The client supplied arguments to NetConnection.connect()
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
    handshake = handshake.ServerNegotiator

    upstreamBandwidth = 2500000L
    downstreamBandwidth = 2500000L
    fmsVer = versions.FMS_MIN_H264

    def __init__(self, applications=None):
        self.applications = {}
        self._pendingApplications = {}

        if applications:
            for name, app in applications.items():
                self.registerApplication(name, app)


    def buildHandshakeNegotiator(self, observer, output):
        """
        Returns a negotiator capable of handling server side handshakes.
        """
        return self.handshake(observer, output)


    def getApplicationWithDefault(self, params, *args):
        """
        Checks if an application exists within the static table. If an
        application cannot be found there, getApplication is called.

        @param args: arguments from RTMP connect packet
        """
        try:
            appName = params['app']
        except KeyError:
            raise exc.ConnectFailed("Bad connect packet (missing 'app' key)")

        if appName in self.applications:
            return self.applications[appName]

        app = self.getApplication(params, *args)

        if app is None:
            raise exc.InvalidApplication("Unknown application '%s'" % (appName,))

        return app

    def getApplication(self, params, *args):
        """
        Returns the active L{IApplication} instance related to C{args}. If
        there is no active application, C{None} is returned.

        @param args: arguments from RTMP connect packet
        """
        return None


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

            app.onAppStart()

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
        app = self._pendingApplications.pop(name, None)

        if app is not None:
            return defer.succeed(app)

        try:
            app = self.applications[name]
        except KeyError:
            raise exc.InvalidApplication("Unknown application '%s'" % (name,))

        # TODO: run through the attached clients and signal the app shutdown.
        d = defer.maybeDeferred(app.shutdown)

        def cb(res):
            app = self.applications.pop(name)
            app.factory = None
            app.name = None

            return app

        d.addBoth(cb)

        return d
