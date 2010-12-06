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

from twisted.python import failure, log
from twisted.internet import defer

from rtmpy import exc
from rtmpy.core import message, status


#: A dictionary of
_exposed_funcs = {}



def expose(func):
    """
    A decorator that provides an easy way to expose methods that the peer can
    'call' via RTMP C{invoke} or C{notify} messages.

    Example usage::

        @expose
        def someRemoteMethod(self, foo, bar):
            pass

        @expose('foo-bar')
        def anotherExposedMethod(self, *args):
            pass

    If expose is called with no args, the function name is used.
    """
    if hasattr(func, '__call__'):
        _exposed_funcs[func.func_name] = func.func_name

        return func

    def decorator(f):
        _exposed_funcs[func] = f.func_name

        return f

    return decorator


class RemoteCallFailed(failure.Failure):
    """
    """


class ExtraResult(object):
    """
    """

    def __init__(self, result, extra=None):
        self.result = result
        self.extra = extra


class BaseStream(object):
    """
    """

    def __init__(self, streamId):
        self.streamId = streamId

        self.timestamp = 0
        self.lastInvokeId = -1
        self.activeInvokes = {}

    def reset(self):
        # TODO: check active invokes and errback
        self.timestamp = 0
        self.lastInvokeId = -1
        self.activeInvokes = {}

    def call(self, name, *args, **kwargs):
        whenDone = kwargs.get('whenDone', None)

        if not whenDone:
            self.sendMessage(message.Invoke(name, 0, None, *args))

            return

        self.lastInvokeId += 1
        invokeId = self.lastInvokeId

        d = defer.Deferred()
        m = message.Invoke(name, invokeId, None, *args)
        self.activeInvokes[invokeId] = d

        self.sendMessage(m, whenDone=whenDone)

        return d

    def sendStatus(self, code_or_status, command=None, **kwargs):
        """
        Informs the peer of a change of status.

        @param code_or_status: A status message or L{status.Status} instance.
            If a string is supplied it will be converted to an L{status.Status}.
        @param command: The command object part of the L{message.Invoke}
            message. Not quite sure what this achieves right now. Defaults to
            L{None}.
        @param kwargs: If a string status message is supplied then any extra
            kwargs will form part of the generated L{status.Status} message.
        """
        if isinstance(code_or_status, status.Status):
            status_obj = code_or_status
        else:
            status_obj = status.status(code_or_status, **kwargs)

        msg = message.Invoke('onStatus', 0, *[command, status_obj])

        self.sendMessage(msg)

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

    def _handleInvokeResponse(self, result, id_):
        """
        Called to handle the response to an invoked method
        """
        if id_ == 0:
            return result

        d = self.activeInvokes.pop(id_, None)

        if d is None:
            self.sendMessage(message.Invoke('_error', id_, None, {}))

            raise RuntimeError('Missing activeInvoke for id %r' % (id_,))

        def write_error(fail):
            code = getattr(fail.type, 'code', 'NetConnection.Call.Failed')

            msg = message.Invoke('_error', id_, None, {
                'level': 'error',
                'code': code,
                'description': fail.getErrorMessage()
            })

            self.sendMessage(msg)

            return fail

        def write_result(result):
            if isinstance(result, ExtraResult):
                msg = message.Invoke('_result', id_, result.extra, result.result)
            else:
                msg = message.Invoke('_result', id_, None, result)

            self.sendMessage(msg)

            return result

        d.addCallbacks(write_result, write_error)

        return result

    def _callExposedMethod(self, name, *args):
        """
        Returns a L{defer.Deferred} that will hold the result of the called
        method.

        @param name: The name of the method to call
        @param args: The supplied args from the invoke/notify call.
        """
        d = defer.Deferred()

        # a request from the peer to call a local method
        try:
            func = self.getInvokableTarget(name)
        except Exception:
            d.errback()

            return d

        if len(args) >= 1 and args[0] is None:
            args = args[1:]

        if func is None:
            d.errback(exc.CallFailed('Unknown method %r' % (name,)))
        else:
            d = defer.maybeDeferred(func, *args)

        return d

    def onInvoke(self, name, id_, args, timestamp):
        """
        Called when an invoke message has been received from the peer. This
        could be a request or a response depending on whether id_ is 'in use'.

        @return: A deferred containing the result of the invoke call. This is
            not strictly necessary but useful for testing purposes.
        @retype: L{defer.Deferred}
        """
        d = self.activeInvokes.pop(id_, None)

        if d:
            # handle the response
            if name == '_error':
                d.errback(RemoteCallFailed(args))
            elif name == '_result':
                d.callback(*args)
            else:
                log.msg('Unhandled name for invoke response %r' % (name,))

            return d

        d = self._callExposedMethod(name, *args)

        if id_ > 0:
            self.activeInvokes[id_] = d

        d.addBoth(self._handleInvokeResponse, id_)

        return d

    def onNotify(self, name, args, timestamp):
        """
        Call an exposed method on this peer but without regard to any return
        value.

        @param name: The name of the method to call
        @param args: A list of arguments for this method.
        @param timestamp: The timestamp at which this notify was called.
        """
        self._callExposedMethod(name, *args)


    def getInvokableTarget(self, name):
        """
        Used to match a callable based on the supplied name when a notify or
        invoke is encountered. Returns C{None} if not found.

        This allows fine grained control over what this stream can expose to the
        peer.

        @param name: The name of the function to be mapped to a callable.
        @return: A callable or C{None}
        """
        func_name = _exposed_funcs.get(name, None)

        if not func_name:
            return

        return getattr(self, func_name)


    def sendMessage(self, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. This a low level method and is not
        part of any public api. If its use is necessary then this is a bug.

        Must be implemented by subclasses.

        @param msg: The RTMP message to be sent by this stream.
        @type: L{message.Message}
        @param whenDone: An optional callback that is fired once the complete
            encoded RTMP message has been sent to the peer. This is not the same
            as a U{defer.Deferred} instance. When called it receives no params.
        """
        raise NotImplementedError



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


    def sendMessage(self, msg, whenDone=None):
        """
        Sends an RTMP message to the peer. This a low level method and is not
        part of any public api. If its use is necessary then this is a bug.

        @param msg: The RTMP message to be sent by this stream.
        @type: L{message.Message}
        @param whenDone: An optional callback that is fired once the complete
            encoded RTMP message has been sent to the peer. This is not the same
            as a U{defer.Deferred} instance. When called it receives no params.
        """
        self.nc.sendMessage(msg, whenDone, stream=self)


    @expose
    def closeStream(self):
        """
        """


class BaseStreamManager(object):
    """
    Handles all stream based operations.

    Stream ID 0 is special, it is considered as the C{NetConnection} stream.

    @ivar _streams: A C{dict} of id -> stream instances.
    @ivar _deletedStreamIds: A collection of stream ids that been deleted and
        can be reused.
    """


    def __init__(self):
        self._streams = {
            0: self
        }

        self._deletedStreamIds = collections.deque()


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
        s = self._streams.get(streamId, None)

        if s is None:
            # the peer needs to call 'createStream' to make new streams.
            raise KeyError('Unknown stream %r' % (streamId,))

        return s


    @expose
    def deleteStream(self, streamId):
        """
        Deletes an existing stream.

        @param streamId: The id of the stream to delete.
        """
        if streamId == 0:
            # TODO: Think about going boom if this is attempted
            return # can't delete the NetConnection

        stream = self._streams.pop(streamId, None)

        if not stream:
            log.msg('Attempted to delete non-existant RTMP stream %r', streamId)
        else:
            self._deletedStreamIds.append(streamId)
            stream.closeStream()


    @expose
    def createStream(self):
        """
        Creates a new stream assigns it a free id.

        @see: L{buildStream}
        """
        try:
            streamId = self._deletedStreamIds.popleft()
        except IndexError:
            streamId = len(self._streams)

        self._streams[streamId] = self.buildStream(streamId)

        return streamId


    def closeAllStreams(self):
        """
        Closes all streams and deletes them from this manager.
        """
        streams = self._streams.copy()

        streams.pop(0, None)

        for streamId, stream in streams.items():
            stream.closeStream()
            self.deleteStream(streamId)
