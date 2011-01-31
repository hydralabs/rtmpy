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
from zope.interface import Interface, implements

from rtmpy import message, rpc, status
from rtmpy.rpc import expose



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


    @expose
    def deleteStream(self, streamId):
        """
        Deletes an existing stream.

        @param streamId: The id of the stream to delete.
        @type streamId: C{int}
        """
        if streamId == self.CONTROL_STREAM_ID:
            log.msg('Attempted to delete RTMP control stream')
            return # can't delete the control stream

        stream = self.streams.pop(streamId, None)

        if stream is None:
            log.msg('Attempted to delete non-existant RTMP stream %r', streamId)

            return

        self._deletedStreamIds.append(streamId)
        stream.closeStream()


    @expose
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

        self.streams = {
            self.CONTROL_STREAM_ID: control_stream
        }



class BaseStream(rpc.AbstractCallHandler):
    """
    """

    def __init__(self, streamId):
        self.streamId = streamId

        self.timestamp = 0


    def sendStatus(self, status, command=None, **kwargs):
        """
        Informs the peer of a change of status.

        @param status: A L{status.IStatus} instance.
        @param command: The command object part of the L{message.Invoke}
            message. Not quite sure what this achieves right now. Defaults to
            L{None}.
        @param kwargs: If a string status message is supplied then any extra
            kwargs will form part of the generated L{status.Status} message.
        """
        self.execute('onStatus', command, status)


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
        else:
            if timestamp < self.timestamp:
                raise ValueError('Cannot set a negative timestamp')

            self.timestamp = timestamp



class NetStream(BaseStream):
    """
    A stream within an RTMP connection. A stream can either send or receive
    video/audio, or in the Flash vernacular - publish or subscribe.

    Not sure about data just yet.
    """

    def __init__(self, nc, streamId):
        BaseStream.__init__(self, streamId)

        self.nc = nc


    @property
    def client(self):
        return self.nc.client


    def sendMessage(self, msg):
        """
        Sends an RTMP message to the peer. This a low level method and is not
        part of any public api. If its use is necessary then this is a bug.

        @param msg: The RTMP message to be sent by this stream.
        @type: L{message.Message}
        """
        self.nc.sendMessage(msg, stream=self)


    @expose
    def closeStream(self):
        """
        """
