# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.event}.
"""

from twisted.trial import unittest
from twisted.internet import defer
from twisted.python.failure import Failure
from zope.interface import implements

from rtmpy.rtmp import interfaces, event


class MockEvent(object):
    """
    """

    implements(interfaces.IEvent)

    expected_encode = None
    expected_decode = None

    encode_func = lambda bbs: None
    decode_func = lambda bbs: None

    def encode(self, bbs):
        self.encode_func(bbs)

        return self.expected_encode

    def decode(self, bbs):
        self.decode_func(bbs)

        return self.expected_decode


class BaseTestCase(unittest.TestCase):
    """
    Ensures that L{event.TYPE_MAP} is properly restored.
    """

    def setUp(self):
        self._type_map = event.TYPE_MAP.copy()
        self._mock_dict = MockEvent.__dict__.copy()

    def tearDown(self):
        event.TYPE_MAP = self._type_map

        for k, v in self._mock_dict.iteritems():
            if not k.startswith('_'):
                setattr(MockEvent, k, v)

    def _fail(self, r):
        print r, str(r.value)
        self.fail()


class DecodeTestCase(BaseTestCase):
    """
    Tests for L{event.decode}
    """

    def test_return_type(self):
        d = event.decode(None, None).addErrback(lambda f: None)

        self.assertTrue(isinstance(d, defer.Deferred))

    def test_unknown_type(self):
        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, event.DecodeError)

            self.assertEquals(str(f.value), 'Unknown datatype \'None\'')

        return event.decode(None, None).addErrback(eb)

    def test_trailing_data(self):
        body = 'foo.bar'
        self.executed = False

        def decode(event, bbs):
            self.executed = True
            bbs.read(4)

        MockEvent.decode_func = decode

        event.TYPE_MAP[0] = MockEvent

        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, event.TrailingDataError)

            self.assertEquals(str(f.value), '')
            self.assertTrue(self.executed)

        return event.decode(0, body).addCallback(self._fail).addErrback(eb)

    def test_return(self):
        body = 'foo.bar'
        self.executed = False

        def decode(event, bbs):
            self.executed = True
            bbs.read(7)

        MockEvent.decode_func = decode

        event.TYPE_MAP[0] = MockEvent

        def cb(r):
            self.assertTrue(isinstance(r, MockEvent))
            self.assertTrue(self.executed)

        return event.decode(0, body).addCallback(cb).addErrback(self._fail)


class EncodeTestCase(BaseTestCase):
    """
    Tests for L{event.encode}
    """

    def test_return_type(self):
        d = event.encode(None).addErrback(lambda f: None)

        self.assertTrue(isinstance(d, defer.Deferred))

    def test_interface(self):
        x = object()

        self.assertFalse(interfaces.IEvent.implementedBy(x))

        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, TypeError)

            self.assertEquals(str(f.value),
                "Expected an event interface (got:<type 'object'>)")

        return event.encode(x).addCallback(self._fail).addErrback(eb)

    def test_unknown_type(self):
        self.assertFalse(MockEvent in event.TYPE_MAP.values())
        x = MockEvent()

        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, event.EncodeError)

            self.assertEquals(str(f.value), 'Unknown event type for %r' % x)

        return event.encode(x).addCallback(self._fail).addErrback(eb)

    def test_return(self):
        def encode(event, bbs):
            bbs.write('foo.bar')

        MockEvent.encode_func = encode
        event.TYPE_MAP[0] = MockEvent

        def cb(b):
            self.assertEquals(b, (0, 'foo.bar'))

        x = MockEvent()

        return event.encode(x).addErrback(self._fail).addCallback(cb)


class BaseEventTestCase(unittest.TestCase):
    """
    Tests for L{event.BaseEvent}
    """

    def test_interface(self):
        x = event.BaseEvent()

        self.assertTrue(interfaces.IEvent.providedBy(x))

        self.assertRaises(NotImplementedError, x.encode, None)
        self.assertRaises(NotImplementedError, x.decode, None)
