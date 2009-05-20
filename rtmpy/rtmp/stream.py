# -*- test-case-name: rtmpy.tests.rtmp.test_stream -*-
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
RTMP Stream implementation.

@since: 0.1
"""

from zope.interface import implements
from twisted.internet import defer, reactor

from rtmpy.rtmp import interfaces, event, status


class BufferingChannelObserver(object):
    """
    """

    def __init__(self, stream, channel):
        self.stream = stream
        self.channel = channel
        self.buffer = ''

    def dataReceived(self, data):
        self.buffer += data

    def bodyComplete(self):
        self.stream.eventReceived(self.channel, self.buffer)

    def headerChanged(self, header):
        if header.relative:
            absHeader = self.channel.getHeader()
            datatype = absHeader.datatype

            if header.timestamp is not None:
                self.stream.setTimestamp(datatype, header.timestamp, header.relative)
        else:
            self.stream.setTimestamp(header.datatype, header.timestamp, header.relative)


class StreamingChannelObserver(object):
    """
    """

    def __init__(self, stream, channel):
        self.stream = stream
        self.channel = channel

    def dataReceived(self, data):
        self.stream.dataReceived(data)

    def bodyComplete(self):
        self.stream.channelComplete(self.channel)

    def headerChanged(self, header):
        self.stream.timestamp = header.timestamp


class ControlStream(object):
    """
    """

    def __init__(self, protocol):
        self.protocol = protocol
        self.decodingChannels = {}
        self.encodingChannels = {}
        self.timestamps = {
            'data': 0,
            'video': 0,
            'audio': 0
        }

    def _getTSKey(self, datatype):
        if datatype == event.AUDIO_DATA:
            return 'audio'
        elif datatype == event.VIDEO_DATA:
            return 'video'

        return'data'

    def getTimestamp(self, datatype):
        """
        """
        return self.timestamps[self._getTSKey(datatype)]

    def setTimestamp(self, datatype, time, relative=False):
        """
        """
        key = self._getTSKey(datatype)

        if relative:
            self.timestamps[key] += time
        else:
            self.timestamps[key] = time

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

        '''if interfaces.IStreamable.implementedBy(kls):
            channel.registerObserver(StreamingChannelObserver(self, channel))
        else:'''
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
                channelId, res[1], self.streamId, res[0], self.getTimestamp(res[0]))

        return event.encode(e).addCallback(cb, channelId)


class ServerControlStream(ControlStream):
    """
    """

    def onInvoke(self, invoke):
        """
        """
        def cb(res):
            if not isinstance(res, (tuple, list)):
                res = (None, res)

            s = res[1]

            if isinstance(s, status.Status):
                if s.level == 'error':
                    return event.Invoke('_error', invoke.id, *res)

            return event.Invoke('_result', invoke.id, *res)

        if invoke.name == u'connect':
            def check_error(res):
                if not isinstance(res, event.Invoke):
                    return res

                if res.name == '_error':
                    self.writeEvent(res, channelId=2)
                    self.writeEvent(event.Invoke('close', 0, None), channelId=2)

                    return

                return res

            d = defer.maybeDeferred(self.protocol.onConnect, *invoke.argv)
            d.addCallback(cb).addCallback(check_error)

            return d
        elif invoke.name == u'createStream':
            d = defer.maybeDeferred(self.protocol.createStream)

            d.addCallback(cb)

            return d
        elif invoke.name == u'deleteStream':
            d = defer.maybeDeferred(self.protocol.deleteStream, *invoke.argv[1:])

            d.addCallback(cb)

            return d

        print 'client invoke', invoke

        d = defer.maybeDeferred(getattr(self.protocol.client, invoke.name), *invoke.argv[1:])

        d.addCallback(cb)

        return d

    def onDownstreamBandwidth(self, bandwidth):
        """
        """
        self.protocol.onDownstreamBandwidth(bandwidth)

    def onFrameSize(self, size):
        self.protocol.decoder.setFrameSize(size)


class Stream(ControlStream):
    """
    """

    def sendStatus(self, code, description=None, **kwargs):
        """
        """
        kwargs['code'] = code
        kwargs['description'] = description

        s = status.status(**kwargs)
        e = event.Invoke('onStatus', 0, None, s)

        return self.writeEvent(e, channelId=4)

    def onInvoke(self, invoke):
        """
        """
        print invoke

        c = getattr(self, invoke.name)

        args = invoke.argv[1:]

        return c(*args)

    def publish(self, stream, app):
        """
        """
        d = defer.Deferred()

        self.stream = stream

        def doStatus(res):
            f = self.sendStatus('NetStream.Publish.Start', '%s is now published.' % (stream,), clientid='B.EAgg^4G.')

            f.addCallback(lambda _: d.callback(None))

        s = self.protocol.getStream(0)

        f = s.writeEvent(event.ControlEvent(0, 1), channelId=2)
        f.addCallback(doStatus)

        return d

    def closeStream(self):
        d = defer.Deferred()

        f = self.sendStatus('NetStream.Unpublish.Success', '%s is now unpublished.' % (self.stream,), clientid='B.EAgg^4G.')

        f.addCallback(lambda _: d.callback(None))

        return d

    def onNotify(self, notify):
        print 'notify', notify

    def onAudioData(self, data):
        print 'audio data', self.timestamps['audio']

    def onVideoData(self, data):
        print 'video data', self.timestamps['video']
