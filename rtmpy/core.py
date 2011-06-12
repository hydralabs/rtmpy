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
Core primitives and logic for all things RTMP.
"""

import collections

from twisted.python import log

from rtmpy import rpc, status



class StreamManager(object):
    """
    Handles all stream based operations.

    Stream ID 0 is special, it is considered as the C{NetConnection} stream.

    @ivar streams: A C{dict} of id -> stream instances.
    @ivar _deletedStreamIds: A collection of stream ids that been deleted and
        can be reused.
    """

    CONTROL_STREAM_ID = 0

    def __init__(self):
        """
        Initialises a stream manager.

        @param nc: The NetConnection stream.
        """
        self._deletedStreamIds = collections.deque()
        self.streams = {
            self.CONTROL_STREAM_ID: self.getControlStream()
        }


    def getControlStream(self):
        """
        Get the control stream for this manager. The control stream equivalent
        to the C{NetConnection} in Flash lingo.

        Must be implemented by subclasses.
        """
        raise NotImplementedError


    def buildStream(self, streamId):
        """
        Returns a new stream object to be associated with C{streamId}.

        Must be overridden by subclasses.

        @param streamId: The id of the stream to create.
        @todo: Think about specifying the interface that the returned stream
            must adhere to.
        """
        raise NotImplementedError


    def getStream(self, streamId):
        """
        Returns the stream related to C{streamId}.

        @param streamId: The id of the stream to get.
        """
        s = self.streams.get(streamId, None)

        if s is None:
            # the peer needs to call 'createStream' to make new streams.
            raise KeyError('Unknown stream %r' % (streamId,))

        return s


    def getNextAvailableStreamId(self):
        """
        Return the next available stream id.
        """
        try:
            return self._deletedStreamIds.popleft()
        except IndexError:
            return len(self.streams)


    @rpc.expose
    def deleteStream(self, streamId):
        """
        Deletes an existing stream.

        @param streamId: The id of the stream to delete.
        @type streamId: C{int}
        """
        if streamId == self.CONTROL_STREAM_ID:
            log.msg('Attempted to delete RTMP control stream')

            return

        stream = self.streams.pop(streamId, None)

        if stream is None:
            log.msg('Attempted to delete non-existant RTMP stream %r' % (streamId,))

            return

        self._deletedStreamIds.append(streamId)
        stream.closeStream()


    @rpc.expose
    def createStream(self):
        """
        Creates a new stream assigns it a free id.

        @see: L{buildStream}
        """
        streamId = self.getNextAvailableStreamId()

        self.streams[streamId] = self.buildStream(streamId)

        return streamId


    def closeAllStreams(self):
        """
        Closes all active streams and deletes them from this manager.
        """
        streams = self.streams.copy()

        # can't close the NetConnection stream.
        control_stream = streams.pop(self.CONTROL_STREAM_ID)

        for streamId, stream in streams.items():
            try:
                self.deleteStream(streamId)
            except:
                log.err()

        try:
            control_stream.closeStream()
        except:
            log.err()

        self.streams = {
            self.CONTROL_STREAM_ID: control_stream
        }



class BaseStream(rpc.AbstractCallHandler):
    """
    """


    def __init__(self, streamId):
        super(rpc.AbstractCallHandler, self).__init__()

        self.streamId = streamId
        self.timestamp = 0


    def sendStatus(self, code, description='', command=None, **kwargs):
        """
        Informs the peer of a change of status.

        @param code: A L{status.IStatus} instance.
        @param command: The command object part of the L{message.Invoke}
            message. Not quite sure what this achieves right now. Defaults to
            L{None}.
        """
        if status.IStatus.providedBy(code):
            s = code
        else:
            s = status.status(code, description, **kwargs)

        self.call('onStatus', s, command=command)


    def setTimestamp(self, timestamp, relative=True):
        """
        Sets the timestamp for this stream. The timestamp is measured in
        milliseconds since an arbitrary epoch. This could be since the stream
        started sending or receiving audio/video etc.

        @param relative: Whether the supplied timestamp is relative to the
            previous.
        """
        if relative:
            self.timestamp += timestamp

            return

        self.timestamp = timestamp


    def onInvoke(self, name, callId, args, timestamp):
        """
        Part of the L{message.IMessageListener} interface, responds to RTMP
        invoke messages.

        @param name: The name of the method call.
        @param callId: Used for handling state.
        @param args: A tuple of arguments supplied with the RPC call.
        @param timestamp: A timestamp when the RPC call was made.
        @return: Returns a L{defer.Deferred} that will hold the result of the
           RPC call. A return value is not part of the interface but helps
           greatly with testing.
        """
        command = None

        if len(args) > 0 and args[0] is None:
            command = args[0]
            args = args[1:]

        if self.isCallActive(callId):
            return self.handleResponse(name, callId, args, command=command)

        return self.callReceived(name, callId, *args)


    def onNotify(self, name, args, timestamp):
        """
        Part of the L{message.IMessageListener} interface, responds to RTMP
        notify messages.

        We simply put the notify through as an anonymous invoke call.

        @param name: The name of the method call.
        @param args: A tuple of arguments supplied with the RPC call.
        @param timestamp: A timestamp when the RPC call was made.
        @return: Returns a L{defer.Deferred} that will hold the result of the
           RPC call. A return value is not part of the interface but helps
           greatly with testing.
        """
        self.callReceived(name, rpc.NO_RESULT, *args)



class NetConnection(StreamManager, BaseStream):
    """
    This is the base class for all concrete NetConnection implementations (e.g.
    one for server and another for client).

    This class is akin to the Flash/FMS NetConnection class and provides the
    same interface.

    @ivar client: The client object that is linked to this NetConnection.
    """

    def __init__(self, protocol):
        self.protocol = protocol
        self.client = None

        BaseStream.__init__(self, 0)
        StreamManager.__init__(self)


    def getControlStream(self):
        """
        Needed by L{StreamManager}.

        @see: L{StreamManager.getControlStream}
        """
        return self.protocol


class NetStream(BaseStream):
    """
    A stream within an RTMP connection. A stream can either send or receive
    video/audio, or in the Flash vernacular - publish or subscribe.

    Not sure about data just yet.

    @ivar nc: The controlling L{NetConnection} instance. A stream cannot exist
        without this.
    """

    def __init__(self, nc, streamId):
        BaseStream.__init__(self, streamId)

        self.nc = nc


    @property
    def client(self):
        return self.nc.client


    def sendMessage(self, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. This a low level method and is not
        part of any public api. If its use is necessary then this is a bug.

        @param msg: The RTMP message to be sent by this stream.
        @type: L{message.Message}
        """
        self.nc.sendMessage(msg, stream=self, whenDone=whenDone)


    @rpc.expose
    def closeStream(self):
        """
        Called to close this stream.
        """
