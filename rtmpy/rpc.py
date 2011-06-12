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
API for handling RTMP RPC calls.
"""

from zope.interface import implements
from twisted.python import failure, log
from twisted.internet import defer

from rtmpy import message, exc, status



__all__ = [
    'expose',
    'CommandResult',
    'AbstractCallHandler',
]


#: The id for an RPC call that does not require or expect a response.
NO_RESULT = 0

#: The name of the response for a successful RPC call
RESPONSE_RESULT = '_result'
#: The name of the response for an RPC call that did not succeed.
RESPONSE_ERROR = '_error'



class RemoteCallFailed(failure.Failure):
    """
    A specific failure type when an RPC returns an error response.
    """



class CommandResult(object):
    """
    This is an RPC result object that contains the actual response to the RPC
    call and a command object that gets encoded as part of the RTMP message.
    """

    def __init__(self, result, command):
        self.result = result
        self.command = command


def expose(func):
    """
    A decorator that provides an easy way to expose methods that the peer can
    'call' via RTMP C{invoke} or C{notify} messages.

    Example usage::

        class SomeClass:
            @expose
            def someRemoteMethod(self, foo, bar):
                pass

            @expose('foo-bar')
            def anotherExposedMethod(self, *args):
                pass

    If expose is called with no args, the function name is used.
    """
    import sys

    def add_meta(locals, exposed_name, func_name=None):
        methods = locals.setdefault('__exposed__', {})

        methods[exposed_name] = func_name or exposed_name


    if callable(func):
        frame = sys._getframe(1)
        add_meta(frame.f_locals, func.__name__)

        return func


    def decorator(f):
        frame = sys._getframe(1)
        add_meta(frame.f_locals, func, f.__name__)

        return f

    return decorator



def getExposedMethods(cls):
    """
    Returns a C{dict} of C{exposed name} to C{class method name} for the given
    class object.

    The results of this function are stored on the class in the
    C{__exposed_mro__} slot.

    The class mro is used to descend into the class hierarchy.
    """
    methods = cls.__dict__.get('__exposed_mro__', None)

    if methods is not None:
        return methods

    import inspect

    ret = {}

    for i in inspect.getmro(cls):
        methods = i.__dict__.get('__exposed__', None)

        if methods is not None:
            ret.update(methods)

    cls.__exposed_mro__ = ret

    return ret



def callExposedMethod(obj, name, *args, **kwargs):
    """
    Calls an exposed methood on C{obj}. If the method is not exposed,
    L{exc.CallFailed} will be raised.

    @return: The result of the called method.
    """
    cls = obj.__class__

    methods = getExposedMethods(cls)

    try:
        methodName = methods[name]
        method = getattr(obj, methodName)
    except Exception, e:
        if isinstance(e, AttributeError):
            log.err("'%s' is exposed but %r does not exist on %r " % (
                name, methodName, obj))

        raise exc.CallFailed("Method not found (%s)" % (name,))

    return method(*args, **kwargs)



class BaseCallHandler(object):
    """
    Provides the ability to initiate, track and finish RPC calls. Each RPC call
    is given a unique id.

    Once a call is I{finished}, it is forgotten about. Call ids cannot be
    reused.

    @ivar strict: Whether response/requests should be handled strictly. This is
        focussed around the callId of the request/response rpc.
    @ivar _lastCallId: The value of the last initiated RPC call.
    @type _lastCallId: C{int}
    @ivar _activeCalls: A C{dict} of callId -> context. An active call has been
        I{initiated} but not yet I{finished}.
    """


    def __init__(self, strict=True):
        self._lastCallId = 1
        self._activeCalls = {}

        self.strict = strict


    def isCallActive(self, callId):
        """
        Whether the C{callId} is a valid identifier for a call awaiting a
        result.
        """
        return callId in self._activeCalls


    def getNextCallId(self):
        """
        Returns the next call id that will be returned by L{initiateCall}.

        This method is useful for unit testing.
        """
        return self._lastCallId + 1


    def getCallContext(self, callId):
        """
        Returns the context stored when L{initiateCall} was executed.

        If no active call is found, C{None} will be returned in its place.

        @param callId: The call id returned by the corresponding call to
            L{initiateCall}.
        @rtype: C{tuple} or C{None} if the call is not active.
        @note: Useful for unit testing.
        """
        return self._activeCalls.get(callId, None)


    def initiateCall(self, *args, **kwargs):
        """
        Starts an RPC call and stores any context for the call for later
        retrieval. The call will remain I{active} until L{finishCall} is called
        with the same C{callId}.

        @param args: The context to be stored whilst the call is active.
        @return: A id that uniquely identifies this call.
        @rtype: C{int}
        """
        callId = kwargs.get('callId', None)

        if callId == NO_RESULT:
            return callId

        if callId is None:
            callId = self._lastCallId = self.getNextCallId()
        elif self.isCallActive(callId):
            raise exc.CallFailed(
                'Unable to initiate an already active call %r' % (callId,))

        self._activeCalls[callId] = args

        return callId


    def finishCall(self, callId):
        """
        Called to finish an active RPC call. The RPC call completed successfully
        (with some sort of response).

        @param callId: The call id returned by the corresponding call to
            L{initiateCall} that uniquely identifies the call.
        @return: The context with which this call was initiated or C{None} if no
            active call could be found.
        """
        return self._activeCalls.pop(callId, None)


    def discardCall(self, callId):
        """
        Called to discard an active RPC call. The RPC call was not completed
        successfully.

        The semantics of this method is different to L{finishCall}, it is useful
        for clearing up any active calls that failed for some arbitrary reason.

        @param callId: The call id returned by the corresponding call to
            L{initiateCall} that uniquely identifies the call.
        @return: The context with which this call was initiated or C{None} if no
            active call could be found.
        """
        return self._activeCalls.pop(callId, None)



class AbstractCallHandler(BaseCallHandler):
    """
    Provides an API to make RPC calls and handle the response.
    """

    implements(message.IMessageSender)


    # IMessageSender
    def sendMessage(self, msg):
        """
        Sends a message. Must be implemented by subclasses.

        @param msg: L{message.IMessage}
        """
        raise NotImplementedError


    def call(self, name, *args, **kwargs):
        """
        Builds and sends an RPC call to the receiving endpoint.

        By default, this is a B{fire-and-forget} method, no result is expected
        or will be returned.

        If C{notify=True} is supplied, a L{defer.Deferred} is returned that
        waits for a result. If an error notification is received then the
        C{errback} will be fired.

        @param name: The name of the method to invoke on the receiving endpoint.
        @type name: C{str}
        @param args: The list of arguments to be invoked.
        @param kwargs['command']: The command arg to be sent as part of the RPC
            call. This should only be used in advanced cases and should
            generally be left alone unless you know what you're doing.
        @param kwargs['notify']: Return a L{defer.Deferred} which will hold the
            result of the call.
        @return: By default, C{None} but if C{notify=True} is supplied, a
            L{defer.Deferred} that will hold the result of the call.
        """
        command = kwargs.get('command', None)
        notify = kwargs.get('notify', False)

        if not notify:
            msg = message.Invoke(name, NO_RESULT, command, *args)

            self.sendMessage(msg)

            return

        d = defer.Deferred()
        callId = self.initiateCall(d, name, args, command)
        m = message.Invoke(name, callId, command, *args)

        try:
            self.sendMessage(m)
        except:
            self.discardCall(callId)

            raise

        return d


    def handleResponse(self, name, callId, result, **kwargs):
        """
        Handles the response to a previously initiated RPC call.

        @param name: The name of the response.
        @type name: C{str}
        @param callId: The tracking identifier for the called method.
        @type callId: C{int}
        @param result: The arguments supplied with the response.
        @return: C{None}
        """
        if callId == 1:
            log.msg('Received RPC response for callId == 1')
            log.msg('name=%r, result=%r, kwargs=%r' % (name, result, kwargs))

            if self.strict:
                raise AssertionError("Received response for callId == 1")

        command = kwargs.get('command', None)
        callContext = self.finishCall(callId)

        if callContext is None:
            if callId == NO_RESULT:
                log.msg('Attempted to handle an RPC response when one was not '
                    'expected.')
                log.msg('Response context was %r%r' % (name, result))
            else:
                log.msg('Unknown RPC callId %r for %r with result %r' % (
                    callId, name, result))

            return

        d, originalName, originalArgs, originalCommand = callContext

        if command is not None:
            log.msg('Received command of %r with result %r' % (command, result))
            log.msg('In response to %r%r' % (originalName, originalArgs))

        # handle the response
        if name == RESPONSE_RESULT:
            d.callback(result)
        elif name == RESPONSE_ERROR:
            d.errback(RemoteCallFailed(result))
        else:
            log.msg('Unknown response type %r' % (name,))
            log.msg('Result = %r' % (result,))
            log.msg('Original call was %r%r with command %r' % (
                originalName, originalArgs, originalCommand))

        return d


    def callReceived(self, name, callId, *args):
        """
        Called when an RPC request as been made. Determines which locally
        exposed method to call and then returns a L{defer.Deferred} which
        handles the result.

        RPC methods can return a L{CommandResult} which will supply the command
        arg to the message.

        @param name: The name of the exposed method to be called.
        @type name: C{str}
        @param callId: The callId for the RPC request.
        @type callId: C{int}
        @param args: The args to be called on the exposed method.
        @return: A L{defer.Deferred} containing the result of the call.
        """
        def cb(result):
            if callId == NO_RESULT:
                return result

            self.finishCall(callId)
            command = None

            if isinstance(result, CommandResult):
                command = result.command
                result = result.result

            msg = message.Invoke(RESPONSE_RESULT, callId, command, result)

            self.sendMessage(msg)

            return result


        def eb(fail):
            if callId == NO_RESULT:
                return fail

            self.finishCall(callId)

            error = status.fromFailure(fail, exc.CallFailed)
            msg = message.Invoke(RESPONSE_ERROR, callId, None, error)

            self.sendMessage(msg)

            return fail


        try:
            self.initiateCall(name, callId=callId, *args)
        except:
            return defer.fail().addErrback(eb)

        d = self.callExposedMethod(name, *args)

        d.addCallbacks(cb, eb)

        return d


    def callExposedMethod(self, name, *args):
        """
        Returns a L{defer.Deferred} that will hold the result of the called
        method.

        This api allows subclasses to hook into the calling process.

        @param name: The name of the method to call
        @param args: The supplied args from the invoke/notify call.
        """
        return defer.maybeDeferred(callExposedMethod, self, name, *args)
