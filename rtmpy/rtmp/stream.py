# -*- test-case-name: rtmpy.tests.rtmp.test_stream -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Stream implementation.

@since: 0.1
"""

from urlparse import urlparse
from zope.interface import implements
from twisted.internet import defer, reactor

from rtmpy.rtmp import interfaces, event, status
from rtmpy import util


class BufferingChannelObserver(object):
    """
    """

    def __init__(self, stream, channel):
        self.stream = stream
        self.channel = channel
        self.buffer = util.BufferedByteStream()

    def dataReceived(self, data):
        """
        """
        self.buffer.write(data)

    def bodyComplete(self):
        """
        """
        self.stream.eventReceived(self.channel, self.buffer.getvalue())
        self.buffer.truncate()

    def headerChanged(self, header):
        """
        """
        if header.timestamp is not None:
            self.stream.setTimestamp(header.timestamp, header.relative)


class BaseStream(object):
    """
    """

    def __init__(self, protocol):
        self.protocol = protocol
        self.decodingChannels = {}
        self.encodingChannels = {}
        self.timestamp = 0

    def sendStatus(self, code, description=None, **kwargs):
        """
        """
        kwargs['code'] = code
        kwargs['description'] = description

        s = status.status(**kwargs)
        e = event.Invoke('onStatus', 0, None, s)

        return self.writeEvent(e, channelId=4)

    def setTimestamp(self, time, relative=False):
        """
        """
        if relative:
            self.timestamp += time
        else:
            self.timestamp = time

    def registerChannel(self, channelId):
        """
        """
        channel = self.protocol.encoder.getChannel(channelId)
        self.encodingChannels[channelId] = channel

        return channel

    def channelRegistered(self, channel):
        """
        """
        header = channel.getHeader()
        kls = event.get_type_class(header.datatype)

        channel.registerObserver(BufferingChannelObserver(self, channel))

        self.decodingChannels[header.channelId] = channel

    def channelUnregistered(self, channel):
        """
        """
        header = channel.getHeader()

        try:
            del self.decodingChannels[header.channelId]
        except KeyError:
            pass

    def dispatchEvent(self, e, channel):
        """
        """
        def cb(res):
            if not interfaces.IEvent.providedBy(res):
                return res

            header = channel.getHeader()
            self.writeEvent(res, header.channelId)

        d = defer.maybeDeferred(e.dispatch, self).addCallback(cb)

    def eventReceived(self, channel, data):
        """
        """
        header = channel.getHeader()
        kls = event.get_type_class(header.datatype)

        d = event.decode(header.datatype, data)

        d.addErrback(self.protocol.logAndDisconnect)
        d.addCallback(self.dispatchEvent, channel)

    def writeEvent(self, e, channelId=None):
        """
        """
        def cb(res, channelId):
            channel = None

            if channelId is None:
                channelId = self.protocol.encoder.getNextAvailableChannelId()
            else:
                try:
                    channel = self.encodingChannels[channelId]
                except KeyError:
                    pass

            if channel is None:
                channel = self.registerChannel(channelId)

            return self.protocol.writePacket(
                channelId, res[1], self.streamId, res[0], self.timestamp)

        return event.encode(e).addCallback(cb, channelId)


class ExtendedBaseStream(BaseStream):
    """
    """

    def __init__(self, *args, **kwargs):
        BaseStream.__init__(self, *args, **kwargs)

        self.published = False

    def onInvoke(self, invoke):
        """
        """
        print invoke

        c = getattr(self, invoke.name)

        args = invoke.argv[1:]

        return c(*args)

    def onNotify(self, notify):
        """
        """
        if notify.name == '@setDataFrame' and notify.id == 'onMetaData':
            # hacky
            self.onMetaData(notify.argv[0])

            return

        print 'notify', notify

    def onAudioData(self, data):
        """
        """
        self.stream.audioDataReceived(data)

    def onVideoData(self, data):
        self.stream.videoDataReceived(data)

    def _getStreamName(self, stream):
        """
        """
        x = urlparse(stream)

        try:
            return x[2]
        except:
            return None


class Stream(ExtendedBaseStream):
    """
    """

    def __init__(self, *args, **kwargs):
        ExtendedBaseStream.__init__(self, *args, **kwargs)

        self.stream = None

    def publish(self, stream, app):
        """
        """
        d = defer.Deferred()

        self.application = self.protocol.factory.getApplication(app)
        streamName = self._getStreamName(stream)

        self.stream = self.application.getStream(streamName)
        self.streamName = streamName

        def doStatus(res):
            f = self.sendStatus('NetStream.Publish.Start',
                '%s is now published.' % (stream,), clientid=self.protocol.client.id)

            self.stream.setPublisher(self)
            self.published = True

            f.addCallback(lambda _: d.callback(None))

        s = self.protocol.getStream(0)

        f = s.writeEvent(event.ControlEvent(0, 1), channelId=2)
        f.addCallback(doStatus)

        return d

    def closeStream(self):
        """
        """
        self.stream.removePublisher(self)

        self.published = False

        d = self.sendStatus('NetStream.Unpublish.Success',
            '%s is now unpublished.' % (self.streamName,), clientid=self.protocol.client.id)

        d.addCallback(lambda _: None)

        return d

    def onMetaData(self, data):
        self.stream.onMetaData(data)


class SubscriberStream(object):
    """
    """

    def __init__(self):
        self.subscribers = []

    def addSubscriber(self, subscriber):
        """
        """
        if subscriber in self.subscribers:
            raise ValueError('subscriber %r already exists' % (subscriber,))

        self.subscribers.append(subscriber)

    def removeSubscriber(self, subscriber):
        """
        """
        self.subscribers.remove(subscriber)

    def _notify(self, attr, *args, **kwargs):
        for s in self.subscribers:
            m = getattr(s, attr)

            m(*args, **kwargs)

    def setPublisher(self, publisher):
        """
        """
        self.publisher = publisher

        self._notify('streamPublished')

    def removePublisher(self, publisher):
        """
        """
        self.publisher = None

        self._notify('streamUnpublished')

    def videoDataReceived(self, data):
        self._notify('videoDataReceived', data, self.publisher.timestamp)

    def audioDataReceived(self, data):
        self._notify('audioDataReceived', data, self.publisher.timestamp)

    def onMetaData(self, properties):
        self._notify('onMetaData', properties)
