"""
"""

from twisted.trial import unittest
from twisted.python import failure
from twisted.internet import defer, reactor, protocol
from twisted.test.proto_helpers import StringTransport, StringIOWithoutClosing

from rtmpy import server


class SimpleApplication(object):
    """
    An L{server.IApplication} that returns a deferred for all that it can.
    """

    factory = None
    name = None

    ret = None

    def startup(self):
        return self.ret

    def shutdown(self):
        return self.ret


class ApplicationRegisteringTestCase(unittest.TestCase):
    """
    Tests for L{server.ServerFactory.registerApplication}
    """

    def setUp(self):
        self.factory = server.ServerFactory()
        self.app = SimpleApplication()

    def test_create(self):
        """
        Test initial args for L{server.ServerFactory}
        """
        self.factory = server.ServerFactory({'foo': self.app})

        self.assertEqual(self.factory.applications, {'foo': self.app})

        d = self.app.ret = defer.Deferred()

        self.factory = server.ServerFactory({'foo': self.app})

        self.assertEqual(self.factory.applications, {})

        def cb(res):
            self.assertEqual(self.factory.applications, {'foo': self.app})

        reactor.callLater(0, d.callback, None)

    def test_invalid_pending(self):
        """
        Pending applications cannot be registered twice.
        """
        self.factory._pendingApplications['foo'] = None

        self.assertRaises(server.InvalidApplication,
            self.factory.registerApplication, 'foo', None)

    def test_invalid_active(self):
        """
        Active applications cannot be registered twice.
        """
        self.factory.applications['foo'] = None

        self.assertRaises(server.InvalidApplication,
            self.factory.registerApplication, 'foo', None)

    def test_deferred_startup(self):
        """
        Registering an application can be paused whilst the app is startup is
        called.
        """
        d = self.app.ret = defer.Deferred()
        ret = self.factory.registerApplication('foo', self.app)

        self.assertIsInstance(ret, defer.Deferred)
        self.assertEqual(self.app.factory, None)
        self.assertEqual(self.app.name, None)
        self.assertTrue('foo' in self.factory._pendingApplications)
        self.assertFalse('foo' in self.factory.applications)

        def cb(res):
            self.assertEqual(res, None)

            self.assertIdentical(self.app.factory, self.factory)
            self.assertEqual(self.app.name, 'foo')
            self.assertFalse('foo' in self.factory._pendingApplications)
            self.assertTrue('foo' in self.factory.applications)

        ret.addCallback(cb)

        reactor.callLater(0, d.callback, None)

        return ret

    def test_failed_deferred(self):
        """
        An error in app.startup should stop the registering process
        """
        def blowup():
            raise RuntimeError

        self.patch(self.app, 'startup', blowup)

        ret = self.factory.registerApplication('foo', self.app)

        self.assertIsInstance(ret, defer.Deferred)

        def eb(fail):
            fail.trap(RuntimeError)

            self.assertEqual(self.app.factory, None)
            self.assertEqual(self.app.name, None)
            self.assertFalse('foo' in self.factory._pendingApplications)
            self.assertFalse('foo' in self.factory.applications)

        ret.addErrback(eb)

        return ret


class ApplicationUnregisteringTestCase(unittest.TestCase):
    """
    Tests for L{server.ServerFactory.unregisterApplication}
    """

    def setUp(self):
        self.factory = server.ServerFactory()
        self.app = SimpleApplication()

    def test_not_registered(self):
        """
        Unregistering an unknown app should error.
        """
        self.assertRaises(server.InvalidApplication,
            self.factory.unregisterApplication, 'foo')

    def test_unregister_pending(self):
        """
        Unregistering a pending application should immediately succeed.
        """
        # this never gets its callback fired, meaning that after registering
        # the application, it is considered pending.
        self.app.ret = defer.Deferred()

        self.factory.registerApplication('foo', self.app)

        self.assertTrue('foo' in self.factory._pendingApplications)

        d = self.factory.unregisterApplication('foo')

        def cb(res):
            self.assertIdentical(res, self.app)

        d.addCallback(cb)

        return d

    def test_simple_unregister(self):
        """
        app.shutdown doesn't need to return a deferred
        """
        self.factory.registerApplication('foo', self.app)

        ret = self.factory.unregisterApplication('foo')

        self.assertIsInstance(ret, defer.Deferred)

        def cb(res):
            self.assertIdentical(res, self.app)

            self.assertEqual(self.app.factory, None)
            self.assertEqual(self.app.name, None)
            self.assertFalse('foo' in self.factory._pendingApplications)
            self.assertFalse('foo' in self.factory.applications)

        ret.addCallback(cb)

        return ret

    def test_deferred(self):
        """
        app.shutdown can return a deferred
        """
        self.factory.registerApplication('foo', self.app)
        d = self.app.ret = defer.Deferred()

        ret = self.factory.unregisterApplication('foo')

        self.assertIsInstance(ret, defer.Deferred)

        def cb(res):
            self.assertIdentical(res, self.app)

            self.assertEqual(self.app.factory, None)
            self.assertEqual(self.app.name, None)
            self.assertFalse('foo' in self.factory._pendingApplications)
            self.assertFalse('foo' in self.factory.applications)

        ret.addCallback(cb)

        reactor.callLater(0, d.callback, None)

        return ret

    def test_deferred_failure(self):
        """
        Removing the app from the factory should not fail due to app.shutdown
        erroring.
        """
        self.factory.registerApplication('foo', self.app)

        d = self.app.ret = defer.Deferred()

        def boom(res):
            self.executed = True

            raise RuntimeError

        d.addCallback(boom)

        ret = self.factory.unregisterApplication('foo')

        self.assertIsInstance(ret, defer.Deferred)

        def cb(res):
            self.assertIdentical(res, self.app)
            self.assertTrue(self.executed)

            self.assertEqual(self.app.factory, None)
            self.assertEqual(self.app.name, None)
            self.assertFalse('foo' in self.factory._pendingApplications)
            self.assertFalse('foo' in self.factory.applications)

        ret.addCallback(cb)

        reactor.callLater(0, d.callback, None)

        return ret


class ServerFactoryTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.factory = server.ServerFactory()
        self.protocol = self.factory.buildProtocol(None)

        self.protocol.connectionMade()
        self.protocol.handshakeSuccess('')

    def test_controlstream(self):
        """
        L{getControlStream}
        """
        s = self.factory.getControlStream(self.protocol, 0)

        self.assertIsInstance(s, server.ServerControlStream)

        self.assertIdentical(s.protocol, self.protocol)


class ConnectingTestCase(unittest.TestCase):
    """
    Tests all facets of connecting to an RTMP server.
    """

    def setUp(self):
        self.file = StringIOWithoutClosing()
        self.transport = protocol.FileWrapper(self.file)

        self.factory = server.ServerFactory()
        self.protocol = self.factory.buildProtocol(None)

        self.protocol.transport = self.transport
        self.protocol.connectionMade()
        self.protocol.handshakeSuccess('')

        self.control = self.protocol.getStream(0)
        isinstance(self.control, server.ServerControlStream)

    def connect(self, packet):
        return self.control.onInvoke('connect', None, [packet], 0)

    def test_missing_app_key(self):
        """
        RTMP connect packets contain {'app': 'name_of_app'}.
        """
        d = self.connect({})

        def cb(r):
            self.fail('Missing app key')

        def eb(fail):
            fail.trap(server.ConnectFailed)

            isinstance(fail, failure.Failure)
            self.assertEqual(fail.getErrorMessage(),
                "Bad connect packet (missing 'app' key)")

        d.addCallback(cb).addErrback(eb)

        return d
