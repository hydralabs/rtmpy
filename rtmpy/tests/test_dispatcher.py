# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.dispatcher}
"""

from twisted.trial import unittest
from twisted.internet import defer

from rtmpy import dispatcher


class MethodWrapperTestCase(unittest.TestCase):
    def test_create(self):
        x = dispatcher._MethodWrapper(ord)

        self.assertEquals(x.method, ord)
        self.assertEquals(x.args, ())
        self.assertEquals(x.kwargs, {})

        x = dispatcher._MethodWrapper(chr, 1, 2, foo='bar')

        self.assertEquals(x.method, chr)
        self.assertEquals(x.args, (1, 2))
        self.assertEquals(x.kwargs, {'foo': 'bar'})

    def test_call(self):
        expected_args = ()
        expected_kwargs = {}
        self._called = False

        def foo(*args, **kwargs):
            self._called = True
            self.assertEquals(args, expected_args)
            self.assertEquals(kwargs, expected_kwargs)

        x = dispatcher._MethodWrapper(foo)

        x()
        self.assertTrue(self._called)

        x = dispatcher._MethodWrapper(foo)

        expected_args = ('a', 'b')
        expected_kwargs = {'some': 1, 'kwarg': 2}
        x('a', 'b', some=1, kwarg=2)

        x = dispatcher._MethodWrapper(foo, [], (), spam='eggs')

        expected_args = ([], ())
        expected_kwargs = {'spam': 'eggs'}
        x()

        expected_args = ([], (), 'a', 'b')
        expected_kwargs = {'spam': 'bar'}
        x('a', 'b', spam='bar')

class CallbackListTestCase(unittest.TestCase):
    def test_create(self):
        x = dispatcher.CallbackList()

        self.assertEquals(x.callbacks, {})

    def test_add(self):
        x = dispatcher.CallbackList()
        self.assertFalse(str in x.callbacks.keys())
        x.addCallback(str, 1, 2, foo='bar')

        self.assertTrue(str in x.callbacks.keys())
        mw = x.callbacks[str]

        self.assertTrue(isinstance(mw, dispatcher._MethodWrapper))
        self.assertTrue(mw.method, str)
        self.assertTrue(mw.args, (1, 2))
        self.assertTrue(mw.kwargs, {'foo': 'bar'})

    def test_add_duplicate(self):
        x = dispatcher.CallbackList()

        x.addCallback(str, 1, 2, foo='bar')
        x.addCallback(str, 3, 4)

        self.assertTrue(str in x.callbacks.keys())
        mw = x.callbacks[str]

        self.assertTrue(isinstance(mw, dispatcher._MethodWrapper))
        self.assertTrue(mw.method, str)
        self.assertTrue(mw.args, (1, 2))
        self.assertTrue(mw.kwargs, {'foo': 'bar'})

    def test_remove(self):
        x = dispatcher.CallbackList()
        x.addCallback(str)

        self.assertTrue(str in x.callbacks.keys())

        x.removeCallback(str)
        self.assertFalse(str in x.callbacks.keys())

        try:
            x.removeCallback(str)
        except:
            self.fail("exception raised when removing non-existant callback")

    def test_empty(self):
        x = dispatcher.CallbackList()
        self.assertTrue(x.isEmpty())
        x.addCallback(str)
        self.assertFalse(x.isEmpty())


class CallbackListCallbackTestCase(unittest.TestCase):
    def setUp(self):
        self.expected_args = tuple()
        self.expected_kwargs = dict()
        self.require_execute = True
        self.executed = False

        self.cbl = dispatcher.CallbackList()

    def tearDown(self):
        if self.require_execute:
            self.assertTrue(self.executed)
        else:
            self.assertFalse(self.executed)

    def _cb(self, *args, **kwargs):
        self.executed = True
        self.assertEquals(args, self.expected_args)
        self.assertEquals(kwargs, self.expected_kwargs)

    def test_empty(self):
        self.require_execute = False

        self.cbl.callback()

    def test_simple(self):
        self.cbl.addCallback(self._cb)

        self.cbl.callback()

    def test_args(self):
        self.expected_args = (1, 2, 3)
        self.expected_kwargs = {'foo': 'bar', 'spam': 'eggs'}

        self.cbl.addCallback(self._cb)

        self.cbl.callback(1, 2, 3, foo='bar', spam='eggs')


class EventDispatcherTestCase(unittest.TestCase):
    def test_interface(self):
        self.assertTrue(dispatcher.IEventDispatcher.implementedBy(
            dispatcher.EventDispatcher))

    def test_create(self):
        x = dispatcher.EventDispatcher()

        self.assertEquals(x.listeners, {})
        self.assertEquals(x._dispatchDepth, 0)
        self.assertEquals(x._updateQueue, [])

    def test_add_simple(self):
        x = dispatcher.EventDispatcher()

        self.assertEquals(x.listeners.keys(), [])
        fn = lambda: None
        x.addEventListener('test', fn)

        self.assertEquals(x.listeners.keys(), [0])
        self.assertEquals(['test'], x.listeners[0].keys())
        cbl = x.listeners[0]['test']
        self.assertEquals(cbl.callbacks.keys(), [fn])

        func = cbl.callbacks[fn]
        self.assertEquals(func.args, tuple())
        self.assertEquals(func.kwargs, {})

    def test_add_args(self):
        x = dispatcher.EventDispatcher()

        fn = lambda: None
        x.addEventListener('test', fn, 0, 1, 2, 3, foo='bar', spam='eggs')

        cbl = x.listeners[0]['test']
        func = cbl.callbacks[fn]

        self.assertEquals(func.args, (1, 2, 3))
        self.assertEquals(func.kwargs, {'foo': 'bar', 'spam': 'eggs'})

    def test_add_priority(self):
        x = dispatcher.EventDispatcher()

        fn = lambda: None
        x.addEventListener('test', fn, -5)

        self.assertTrue(-5 in x.listeners.keys())
        self.assertFalse(0 in x.listeners.keys())

    def test_add_existing_priority(self):
        x = dispatcher.EventDispatcher()

        y = {}
        x.listeners[0] = y

        self.assertIdentical(x.listeners[0], y)

        fn = lambda: None
        x.addEventListener('test', fn)

        self.assertEquals(y.keys(), ['test'])

    def test_add_existing_event_type(self):
        x = dispatcher.EventDispatcher()

        y = {}
        x.listeners[0] = y

        self.assertIdentical(x.listeners[0], y)
        x.addEventListener('test', lambda: None)

        cbl = x.listeners[0]['test']

        fn = lambda: None
        x.addEventListener('test', fn)

        self.assertTrue(fn in cbl.callbacks)

    def test_add_in_dispatch(self):
        x = dispatcher.EventDispatcher()
        x._dispatchDepth = 1

        self.assertEquals(x._updateQueue, [])

        fn = lambda: None
        x.addEventListener('test', fn)

        self.assertNotEquals(x._updateQueue, [])
        self.assertEquals(len(x._updateQueue), 1)

        cb = x._updateQueue[0]
        x._dispatchDepth = 0

        cb()

        self.assertEquals(x.listeners.keys(), [0])
        self.assertEquals(['test'], x.listeners[0].keys())
        cbl = x.listeners[0]['test']
        self.assertEquals(cbl.callbacks.keys(), [fn])

        func = cbl.callbacks[fn]
        self.assertEquals(func.args, tuple())
        self.assertEquals(func.kwargs, {})

    def test_remove_simple(self):
        x = dispatcher.EventDispatcher()
        x.addEventListener('foo', ord)

        cbl = x.listeners[0]['foo']
        self.assertTrue(ord in cbl.callbacks)

        x.removeEventListener('foo', ord)
        self.assertFalse(ord in cbl.callbacks)

        self.assertTrue(0 in x.listeners)
        self.assertTrue('foo' in x.listeners[0])

    def test_remove_priority(self):
        x = dispatcher.EventDispatcher()
        x.addEventListener('foo', ord, 10)

        cbl = x.listeners[10]['foo']
        self.assertTrue(ord in cbl.callbacks)

        x.removeEventListener('foo', ord)
        self.assertFalse(ord in cbl.callbacks)

        self.assertTrue(10 in x.listeners)
        self.assertTrue('foo' in x.listeners[10])

    def test_remove_in_dispatch(self):
        x = dispatcher.EventDispatcher()

        fn = lambda: None
        x.addEventListener('spam', fn)

        x._dispatchDepth = 1
        self.assertEquals(x._updateQueue, [])
        x.removeEventListener('spam', fn)

        self.assertNotEquals(x._updateQueue, [])
        self.assertEquals(len(x._updateQueue), 1)

        cb = x._updateQueue[0]
        x._dispatchDepth = 0

        cb()

        self.assertEquals(x.listeners.keys(), [0])
        self.assertEquals(['spam'], x.listeners[0].keys())
        cbl = x.listeners[0]['spam']
        self.assertEquals(cbl.callbacks.keys(), [])

    def test_has_event_listener(self):
        x = dispatcher.EventDispatcher()

        self.assertFalse(x.hasEventListener('xyz'))
        x.addEventListener('xyz', lambda: None)
        self.assertTrue(x.hasEventListener('xyz'))


class DispatchEventTestCase(unittest.TestCase):
    def test_order(self):
        self.order = []
        def a():
            self.order.append('a')

        def b():
            self.order.append('b')

        x = dispatcher.EventDispatcher()

        x.addEventListener('abc', a)
        x.addEventListener('abc', b)

        x._dispatchEvent('abc')

        self.assertEquals(self.order, ['a', 'b'])

    def test_priorities(self):
        self.order = []
        def a():
            self.order.append('a')

        def b():
            self.order.append('b')

        x = dispatcher.EventDispatcher()

        x.addEventListener('abc', a, 0)
        x.addEventListener('abc', b, 10)

        x._dispatchEvent('abc')

        self.assertEquals(self.order, ['b', 'a'])

    def test_multiple(self):
        self.order = []
        def a():
            self.order.append('a')

        def b():
            self.order.append('b')

        x = dispatcher.EventDispatcher()

        x.addEventListener('abc', a)
        x.addEventListener('abc', b)

        x._dispatchEvent('abc')

        self.assertTrue('a' in self.order)
        self.assertTrue('b' in self.order)

    def test_dispatch_depth(self):
        self.order = []
        def a(ev):
            self.order.append('a')
            self.assertTrue(ev._dispatchDepth, 1)

        def b(ev):
            self.order.append('b')
            ev._dispatchEvent('xyz')

        def c(ev):
            self.order.append('c')
            self.assertTrue(ev._dispatchDepth, 2)

        x = dispatcher.EventDispatcher()
        x.addEventListener('123', a, 0, x)
        x.addEventListener('123', b, 0, x)
        x.addEventListener('xyz', c, 0, x)

        x._dispatchEvent('123')
        self.assertTrue('a' in self.order)
        self.assertTrue('b' in self.order)
        self.assertTrue('c' in self.order)

    def test_empty_list(self):
        x = dispatcher.EventDispatcher()

        cbl = dispatcher.CallbackList()
        x.listeners = {0: {'foo': cbl}}

        x._dispatchEvent('foo')

        self.assertEquals(x.listeners, {0: {}})

    def test_update_queue(self):
        x = dispatcher.EventDispatcher()

        self.called = False

        def cb():
            self.called = True

        x._updateQueue = [cb]

        x._dispatchEvent('123')

        self.assertEquals(x._updateQueue, [])
        self.assertTrue(self.called)
        self.assertEquals(x._dispatchDepth, 0)

    def test_main_func(self):
        d = defer.Deferred()

        def cb():
            d.callback(None)

        x = dispatcher.EventDispatcher()

        x.addEventListener('123', cb)
        x.dispatchEvent('123')

        return d
