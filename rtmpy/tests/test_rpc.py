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
Tests for L{rtmpy.rpc}.
"""


from twisted.trial import unittest
from twisted.internet import defer

from rtmpy import rpc, message, exc



class ExposingTestCase(unittest.TestCase):
    """
    Tests for L{rpc.expose}.
    """


    def assertExposed(self, class_func, msg=None):
        cls = class_func.im_class
        name = class_func.__name__

        exposed_methods = rpc.getExposedMethods(cls)

        assert name in exposed_methods, \
            msg or '%r is not an exposed method on %r' % (name, cls)


    def assertExposedAs(self, class_func, as_, msg=None):
        cls = class_func.im_class
        name = class_func.__name__

        exposed_methods = rpc.getExposedMethods(cls)

        assert exposed_methods.get(as_, None) == name, \
            msg or '%r is not an exposed method on %r' % (name, cls)


    def assertNotExposed(self, class_func, msg=None):
        try:
            self.assertExposed(class_func)
        except AssertionError:
            pass
        else:
            cls = class_func.im_class
            name = class_func.__name__

            raise AssertionError(
                msg or '%r IS an exposed method on %r' % (name, cls))


    def test_simple(self):
        """
        Exposing methods on classes should return sane values for
        L{rpc.getExposedMethods}
        """
        class SomeClass(object):
            @rpc.expose
            def foo(self):
                pass


            @rpc.expose('me')
            def bar(self):
                pass


            def not_exposed(self):
                pass

        self.assertEqual(rpc.getExposedMethods(SomeClass),
            {'me': 'bar', 'foo': 'foo'})

        self.assertExposed(SomeClass.foo)
        self.assertNotExposed(SomeClass.not_exposed)
        self.assertExposedAs(SomeClass.bar, 'me')
        self.assertExposedAs(SomeClass.foo, 'foo')


    def test_deep(self):
        """
        As with L{test_simple} but a complex class hierarchy.
        """
        class A(object):
            @rpc.expose
            def anon(self):
                pass

            def nope(self):
                pass

        class B(A):
            @rpc.expose('bar')
            def named(self):
                pass


        self.assertEqual(rpc.getExposedMethods(A), {'anon': 'anon'})
        self.assertEqual(rpc.getExposedMethods(B),
            {'anon': 'anon', 'bar': 'named'})

        self.assertExposedAs(A.anon, 'anon')
        self.assertExposedAs(B.anon, 'anon')
        self.assertNotExposed(A.nope)
        self.assertNotExposed(B.nope)
        self.assertExposedAs(B.named, 'bar')


class CallHandlerTestCase(unittest.TestCase):
    """
    Tests for L{rpc.BaseCallHandler}.
    """

    def setUp(self):
        self.handler = rpc.BaseCallHandler()


    def test_initiate(self):
        """
        Initiating a call should store the context that was passed to the call
        and return a unique, incrementing id.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        self.assertEqual(h.getNextCallId(), 1)
        self.assertEqual(h.getCallContext(1), None)

        self.assertEqual(h.initiateCall(*c), 1)
        self.assertEqual(h.getCallContext(1), c)

        self.assertEqual(h.getNextCallId(), 2)
        self.assertEqual(h.getCallContext(2), None)


    def test_active(self):
        """
        Ensure that L{rpc.BaseCallHandler.isCallActive} returns some sane
        results.
        """
        h = self.handler

        self.assertEqual(h.getNextCallId(), 1)

        self.assertFalse(h.isCallActive(1))

        callId = h.initiateCall()

        self.assertTrue(h.isCallActive(callId))


    def test_finish_non_active(self):
        """
        Finishing a call that is not active should result in no state change
        and C{None} should be returned.
        """
        h = self.handler
        hsh = hash(h)

        self.assertFalse(h.isCallActive(1))

        self.assertEqual(h.finishCall(1), None)
        self.assertEqual(hsh, hash(h))


    def test_finish_active_call(self):
        """
        Finishing an active call should return the original context supplied to
        C{initiateCall} and the call should no longer be active.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        callId = h.initiateCall(*c)

        self.assertEqual(h.finishCall(callId), c)
        self.assertFalse(h.isCallActive(callId))


    def test_discard_non_active(self):
        """
        Discarding a call that is not active should result in no state change
        and C{None} should be returned.
        """
        h = self.handler
        hsh = hash(h)

        self.assertFalse(h.isCallActive(1))

        self.assertEqual(h.discardCall(1), None)
        self.assertEqual(hsh, hash(h))


    def test_discard_active_call(self):
        """
        Discarding an active call should return the original context supplied to
        C{initiateCall} and the call should no longer be active.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        callId = h.initiateCall(*c)

        self.assertEqual(h.discardCall(callId), c)
        self.assertFalse(h.isCallActive(callId))


    def test_initiate_already_active(self):
        """
        Initiating a call with an already active callId should raise an
        L{exc.CallFailed} error.
        """
        h = self.handler

        callId = h.initiateCall()

        self.assertRaises(exc.CallFailed, h.initiateCall, callId=callId)



class AbstractCallHandlerTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractCallHandler}
    """


    def test_interface(self):
        """
        Check defined interfaces.
        """
        self.assertTrue(
            message.IMessageSender.implementedBy(rpc.AbstractCallHandler))


    def test_send_message(self):
        """
        Abstract methods should raise C{NotImplementedError}.
        """
        a = rpc.AbstractCallHandler()

        self.assertRaises(NotImplementedError, a.sendMessage, None)



class SimpleInitiator(rpc.AbstractCallHandler):
    """
    An implementation of L{rpc.AbstractCallInitiator} that stores any messages
    were sent for later inspection.

    @messages
    """

    def __init__(self):
        super(rpc.AbstractCallHandler, self).__init__()

        self.messages = []


    def sendMessage(self, msg):
        """
        Keeps track of any messages that were 'sent'.
        """
        self.messages.append(msg)



class CallTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractCallInitiator.call}
    """


    def setUp(self):
        self.invoker = SimpleInitiator()
        self.messages = self.invoker.messages


    def test_call_message(self):
        """
        Check the context of the message sent when L{callWithoutResult} is
        executed.
        """
        i = self.invoker
        m = self.messages

        ret = i.call('remote_method', 1, 2, 3, 'foo')
        self.assertEqual(ret, None)

        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [None, 1, 2, 3, 'foo'])


    def test_call_command(self):
        """
        Ensure L{execute} accepts a C{command} kwarg and that it is
        set on the message appropriately.
        """
        cmd = {'foo': 'bar'}
        i, m = self.invoker, self.messages

        ret = i.call('remote_method', command=cmd)
        self.assertEqual(ret, None)

        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [cmd])


    def test_call_tracking(self):
        """
        Any call to L{execute} should not be considered 'active'.
        """
        i = self.invoker

        i.call('foo')

        self.assertFalse(i.isCallActive(0))



class CallWithNotifTestCase(unittest.TestCase):
    """
    Tests for L{rpc.AbstractCallHandler.call} with C{notify=True} supplied.
    """


    def setUp(self):
        self.invoker = SimpleInitiator()
        self.messages = self.invoker.messages


    def test_call(self):
        """
        Check the context of the message sent when L{call} is
        executed.
        """
        i = self.invoker
        m = self.messages

        d = i.call('remote_method', 1, 2, 3, 'foo', notify=True)

        self.assertTrue(isinstance(d, defer.Deferred))
        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [None, 1, 2, 3, 'foo'])

        callContext = i.getCallContext(msg.id)

        self.assertEqual(callContext,
            (d, 'remote_method', (1, 2, 3, 'foo'), None))


    def test_command(self):
        """
        Ensure L{call} accepts a C{command} kwarg and that it
        is set on the sent message appropriately.
        """
        cmd = {'foo': 'bar'}
        i, m = self.invoker, self.messages

        d = i.call('remote_method', command=cmd, notify=True)

        self.assertTrue(isinstance(d, defer.Deferred))
        self.assertEqual(len(m), 1)
        msg = m.pop()

        self.assertEqual(message.typeByClass(msg), message.INVOKE)
        self.assertEqual(msg.id, 1)
        self.assertEqual(msg.name, 'remote_method')
        self.assertEqual(msg.argv, [cmd])

        callContext = i.getCallContext(msg.id)

        self.assertEqual(callContext,
            (d, 'remote_method', (), cmd))


    def test_send_failure(self):
        """
        Ensure correct state when sending a message blows up.
        """
        class TestRuntimeError(RuntimeError):
            """
            """

        def sendBadMessage(msg):
            self.msg = msg

            raise TestRuntimeError(msg)

        i = self.invoker

        self.patch(i, 'sendMessage', sendBadMessage)

        self.assertRaises(TestRuntimeError, i.call,
            'remote_method', notify=True)

        self.assertFalse(i.isCallActive(self.msg.id))



class CallResponseTestCase(unittest.TestCase):
    """
    Tests the response to an RPC call.
    """


    def setUp(self):
        self.invoker = SimpleInitiator()
        self.messages = self.invoker.messages


    def sendResponse(self, responseType, callId, *args, **kwargs):
        """
        Build an RPC response.

        @param responseType: Either C{_result} or C{_error}.
        @param callId: The id of the response.
        @param args: The args to supply as part of the response.
        """
        self.invoker.handleResponse(responseType, callId, args, **kwargs)


    def makeCall(self, name, *args, **kwargs):
        """
        """
        kwargs.setdefault('notify', True)

        return self.invoker.call(name, *args, **kwargs)


    def test_unknown_call_id(self):
        """
        Send a response to a non existant RPC call.
        """
        i = self.invoker

        self.assertFalse(i.isCallActive(0))
        self.sendResponse(None, 0)

        self.assertFalse(i.isCallActive(2))
        self.sendResponse(None, 2)


    def test_success_result(self):
        """
        Ensure that the deferred handed back in L{call} has its
        callback called if a success response is received for the corresponding
        call id.

        The callback should contain the args of the response
        """
        d = self.makeCall('some_remote_method')
        self.executed = False

        def cb(args):
            self.executed = True

            self.assertEqual(args, ('foo', 'bar'))

        d.addCallback(cb)

        self.sendResponse('_result', 1, 'foo', 'bar')

        self.assertTrue(self.executed)
        self.assertFalse(self.invoker.isCallActive(2))


    def test_error_result(self):
        """
        Ensure that the deferred handed back in L{call} has its
        errback called if an error response is received for the corresponding
        call id.

        """
        d = self.makeCall('some_remote_method')
        self.executed = False

        def eb(fail):
            self.executed = True

            self.assertIsInstance(fail, rpc.RemoteCallFailed)
            self.assertEqual(fail.value, ('foo', 'bar'))


        d.addCallback(lambda _: self.fail('Callback called'))
        d.addErrback(eb)

        self.sendResponse('_error', 1, 'foo', 'bar')

        self.assertTrue(self.executed)
        self.assertFalse(self.invoker.isCallActive(2))


    def test_command(self):
        """
        Ensure that a command kwarg is acceptable by L{handleResponse}.
        """
        d = self.makeCall('some_remote_method')
        self.executed = False

        def cb(res):
            self.executed = True


        d.addCallback(cb)

        self.sendResponse('_result', 1, 'foo', 'bar', command={'foo': 'bar'})

        self.assertTrue(self.executed)
        self.assertFalse(self.invoker.isCallActive(2))


    def test_unknown_response(self):
        """
        Ensure that the deferred is not called if the response name is not
        recognised.
        """
        d = self.makeCall('some_remote_method')

        d.addBoth(lambda: self.fail('deferred executed!'))

        self.sendResponse('foo', 2, 'some result')

        self.assertFalse(self.invoker.isCallActive(2))



class CallingExposedMethodTestCase(unittest.TestCase):
    """
    Tests for L{rpc.callExposedMethod}
    """

    class Foo(object):
        expectedArgs = None
        expectedReturn = None

        def __init__(self, test):
            self.test = test


        @rpc.expose
        def exposed(self, *args):
            self.test.assertEqual(args, self.expectedArgs)

            return self.expectedReturn


        @rpc.expose('named')
        def exposed_named(self, *args):
            self.test.assertEqual(args, self.expectedArgs)

            return self.expectedReturn


        def not_exposed(self, *args):
            self.test.assertEqual(args, self.expectedArgs)

            return self.expectedReturn


        @rpc.expose
        def deleted_func(self):
            pass


    del Foo.deleted_func


    def setUp(self):
        self.instance = self.Foo(self)


    def call(self, name, expectedArgs, expectedReturn):
        self.instance.expectedArgs = expectedArgs
        self.instance.expectedReturn = expectedReturn

        self.assertEqual(rpc.callExposedMethod(
            self.instance, name, *expectedArgs), expectedReturn)


    def test_exposed_unnamed(self):
        """
        Test unnamed.
        """
        self.call('exposed', (1, 2, 3), 'foo')


    def test_exposed_named(self):
        """
        Test named exposed function for args and return.
        """
        self.call('named', (1, 2, 3), 'foo')
        e = self.assertRaises(exc.CallFailed,
            self.call, 'exposed_named', (1, 2, 3), 'foo')

        self.assertEqual(str(e), "Method not found (exposed_named)")


    def test_not_exposed(self):
        """
        Ensure that calling an unexposed method results in a L{exc.CallFailed}
        exception.
        """
        e = self.assertRaises(exc.CallFailed,
            self.call, 'not_exposed', (), None)

        self.assertEqual(str(e), "Method not found (not_exposed)")


    def test_deleted_func(self):
        """
        Deleting a pre-exposed function should raise an error when calling
        that exposed method.
        """
        e = self.assertRaises(exc.CallFailed,
            self.call, 'deleted_func', (), None)

        self.assertEqual(str(e), "Method not found (deleted_func)")



class TestRuntimeError(RuntimeError):
    """
    A RuntimeError specific to this test suite.
    """



class SimpleFacilitator(rpc.AbstractCallHandler):
    """
    An implementation of L{rpc.AbstractCallHandler} that stores any messages
    were sent for later inspection.

    Exposes a number of simple methods.
    """

    def __init__(self, test):
        super(rpc.AbstractCallHandler, self).__init__()

        self.test = test
        self.messages = []


    def sendMessage(self, msg, whenDone=None):
        """
        Keeps track of any messages that were 'sent'.
        """
        self.messages.append(msg)


    @rpc.expose
    def exposed(self, *args):
        assert args, (1, 2, 3)
        self.test.executed = True


    @rpc.expose('named')
    def exposed_named(self, *args):
        assert args, (1, 2, 3)
        self.test.executed = True


    def not_exposed(self):
        pass


    @rpc.expose
    def known_return(self):
        self.test.executed = True

        return 'foo'


    @rpc.expose
    def known_failure(self):
        self.test.executed = True

        raise TestRuntimeError('This is my BOOOM stick!!')


    @rpc.expose
    def command_result(self):
        return rpc.CommandResult('foo', {'one': 'two'})



class CallReceiverTestCase(unittest.TestCase):
    """
    Tests receiving an RPC call.
    """


    def setUp(self):
        self.receiver = SimpleFacilitator(self)
        self.messages = self.receiver.messages
        self.executed = False

    def makeCall(self, name, *args, **kwargs):
        """
        Makes an RPC call on L{self.receiver}
        """
        return self.receiver.callReceived(
            name, self.receiver.getNextCallId(), *args, **kwargs)


    @defer.inlineCallbacks
    def test_already_active(self):
        """
        If an RPC request with the same callId is made whilst the first request
        is still 'active', an error should be thrown.
        """
        callId = self.receiver.getNextCallId()

        self.receiver.initiateCall(callId=callId)

        try:
            yield self.makeCall('foo', callId)
        except exc.CallFailed, e:
            pass
        else:
            self.fail('exc.CallFailed not raised')

        self.assertEqual(str(e), 'Unable to initiate an already active call 1')
        m = self.messages
        self.assertEqual(len(m), 1)

        msg = self.messages.pop()

        self.assertTrue(message.typeByClass(msg), message.Invoke)
        self.assertEqual(msg.name, '_error')
        self.assertEqual(msg.argv, [None, {
            'code': 'NetConnection.Call.Failed',
            'description': 'Unable to initiate an already active call 1',
            'level': 'error'
        }])
        self.assertEqual(msg.id, callId)


    @defer.inlineCallbacks
    def test_call_exposed(self):
        """
        Call an exposed method on the faciliator.
        """
        ret = yield self.receiver.callExposedMethod('exposed', 1, 2, 3)

        self.assertEqual(ret, None)
        self.assertTrue(self.executed)


    @defer.inlineCallbacks
    def test_call_exposed_named(self):
        """
        Call a named exposed method on the faciliator.
        """
        ret = yield self.receiver.callExposedMethod('named', 1, 2, 3)

        self.assertEqual(ret, None)
        self.assertTrue(self.executed)


    @defer.inlineCallbacks
    def test_call_known_result(self):
        """
        Call an exposed method with a known result
        """
        ret = yield self.receiver.callExposedMethod('known_return')

        self.assertEqual(ret, 'foo')
        self.assertTrue(self.executed)


    @defer.inlineCallbacks
    def test_successful_call(self):
        """
        Test a successful RPC call.
        """
        ret = yield self.makeCall('known_return')

        self.assertEqual(ret, 'foo')

        m = self.messages
        self.assertEqual(len(m), 1)

        msg = self.messages.pop()

        self.assertTrue(message.typeByClass(msg), message.Invoke)
        self.assertEqual(msg.name, '_result')
        self.assertEqual(msg.argv, [None, 'foo'])
        self.assertEqual(msg.id, 1)


    @defer.inlineCallbacks
    def test_failure_call(self):
        """
        Test an RPC call that raises an exception.
        """
        try:
            yield self.makeCall('known_failure')
        except TestRuntimeError, e:
            self.assertEqual(str(e), 'This is my BOOOM stick!!')
        else:
            self.fail('TestRuntimeError not raised.')

        m = self.messages
        self.assertEqual(len(m), 1)

        msg = self.messages.pop()

        self.assertTrue(message.typeByClass(msg), message.Invoke)
        self.assertEqual(msg.name, '_error')
        self.assertEqual(msg.argv, [None, {
            'code': 'NetConnection.Call.Failed',
            'description': 'This is my BOOOM stick!!',
            'level': 'error'
        }])
        self.assertEqual(msg.id, 1)


    @defer.inlineCallbacks
    def test_command_callback(self):
        """
        Test a command result and the message that is generated.
        """
        ret = yield self.makeCall('command_result')

        self.assertEqual(ret, 'foo')

        m = self.messages
        self.assertEqual(len(m), 1)

        msg = self.messages.pop()

        self.assertTrue(message.typeByClass(msg), message.Invoke)
        self.assertEqual(msg.name, '_result')
        self.assertEqual(msg.argv, [{'one': 'two'}, 'foo'])
        self.assertEqual(msg.id, 1)
