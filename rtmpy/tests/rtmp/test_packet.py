# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.packet}.
"""

from twisted.trial import unittest
from twisted.internet import defer
from twisted.python.failure import Failure
from zope.interface import implements
import pyamf

from rtmpy.rtmp import interfaces, packet
from rtmpy.util import BufferedByteStream


class MockPacket(object):
    """
    """

    implements(interfaces.IPacket)

    expected_encode = None
    expected_decode = None

    encode_func = lambda bbs: None
    decode_func = lambda bbs: None

    def encode(self, bbs, *args, **kwargs):
        self.encode_func(bbs, *args, **kwargs)

        return self.expected_encode

    def decode(self, bbs, *args, **kwargs):
        self.decode_func(bbs, *args, **kwargs)

        return self.expected_decode


class BaseTestCase(unittest.TestCase):
    """
    Ensures that L{packet.TYPE_MAP} is properly restored.
    """

    def setUp(self):
        self._type_map = packet.TYPE_MAP.copy()
        self._mock_dict = MockPacket.__dict__.copy()

        self.buffer = BufferedByteStream()

    def tearDown(self):
        packet.TYPE_MAP = self._type_map

        for k, v in self._mock_dict.iteritems():
            if not k.startswith('_'):
                setattr(MockPacket, k, v)

    def _fail(self, r):
        print r, str(r.value)
        self.fail()


class DecodeTestCase(BaseTestCase):
    """
    Tests for L{packet.decode}
    """

    def test_return_type(self):
        d = packet.decode(None, None).addErrback(lambda f: None)

        self.assertTrue(isinstance(d, defer.Deferred))

    def test_unknown_type(self):
        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, packet.DecodeError)

            self.assertEquals(str(f.value), 'Unknown datatype \'None\'')

        return packet.decode(None, None).addErrback(eb)

    def test_trailing_data(self):
        body = 'foo.bar'
        self.executed = False

        def decode(packet, bbs):
            self.executed = True
            bbs.read(4)

        MockPacket.decode_func = decode

        packet.TYPE_MAP[0] = MockPacket

        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, packet.TrailingDataError)

            self.assertEquals(str(f.value), '')
            self.assertTrue(self.executed)

        return packet.decode(0, body).addCallback(self._fail).addErrback(eb)

    def test_return(self):
        body = 'foo.bar'
        self.executed = False

        def decode(packet, bbs):
            self.executed = True
            bbs.read(7)

        MockPacket.decode_func = decode

        packet.TYPE_MAP[0] = MockPacket

        def cb(r):
            self.assertTrue(isinstance(r, MockPacket))
            self.assertTrue(self.executed)

        return packet.decode(0, body).addCallback(cb).addErrback(self._fail)

    def test_args(self):
        args = ('foo', 'bar')
        kwargs = {'baz': 'gak', 'spam': 'eggs'}
        self.executed = False

        def decode(packet, bbs, *a, **kw):
            self.assertEquals(args, a)
            self.assertEquals(kwargs, kw)

            self.executed = True

        MockPacket.decode_func = decode

        packet.TYPE_MAP[0] = MockPacket

        d = packet.decode(0, '', *args, **kwargs)
        d.addCallback(lambda r: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class EncodeTestCase(BaseTestCase):
    """
    Tests for L{packet.encode}
    """

    def test_return_type(self):
        d = packet.encode(None).addErrback(lambda f: None)

        self.assertTrue(isinstance(d, defer.Deferred))

    def test_interface(self):
        x = object()

        self.assertFalse(interfaces.IPacket.implementedBy(x))

        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, TypeError)

            self.assertEquals(str(f.value),
                "Expected an packet interface (got:<type 'object'>)")

        return packet.encode(x).addCallback(self._fail).addErrback(eb)

    def test_unknown_type(self):
        self.assertFalse(MockPacket in packet.TYPE_MAP.values())
        x = MockPacket()

        def eb(f):
            self.assertTrue(isinstance(f, Failure))
            self.assertEquals(f.type, packet.EncodeError)

            self.assertEquals(str(f.value), 'Unknown packet type for %r' % x)

        return packet.encode(x).addCallback(self._fail).addErrback(eb)

    def test_return(self):
        def encode(packet, bbs):
            bbs.write('foo.bar')

        MockPacket.encode_func = encode
        packet.TYPE_MAP[0] = MockPacket

        def cb(b):
            self.assertEquals(b, (0, 'foo.bar'))

        x = MockPacket()

        return packet.encode(x).addErrback(self._fail).addCallback(cb)

    def test_args(self):
        args = ('foo', 'bar')
        kwargs = {'baz': 'gak', 'spam': 'eggs'}
        self.executed = False

        def encode(packet, bbs, *a, **kw):
            self.assertEquals(args, a)
            self.assertEquals(kwargs, kw)

            self.executed = True

        MockPacket.encode_func = encode
        packet.TYPE_MAP[0] = MockPacket

        x = MockPacket()

        d = packet.encode(x, *args, **kwargs)
        d.addCallback(lambda r: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class BasePacketTestCase(unittest.TestCase):
    """
    Tests for L{packet.BasePacket}
    """

    def test_interface(self):
        x = packet.BasePacket()

        self.assertTrue(interfaces.IPacket.providedBy(x))

        self.assertRaises(NotImplementedError, x.encode, None)
        self.assertRaises(NotImplementedError, x.decode, None)


class FrameSizeTestCase(BaseTestCase):
    """
    Tests for L{packet.FrameSize}
    """

    def test_create(self):
        x = packet.FrameSize()
        self.assertEquals(x.__dict__, {'size': None})

        x = packet.FrameSize(10)
        self.assertEquals(x.__dict__, {'size': 10})

        x = packet.FrameSize(size=20)
        self.assertEquals(x.__dict__, {'size': 20})

    def test_raw_encode(self):
        # test default encode
        x = packet.FrameSize()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Frame size not set')

        # test non-int encode
        x = packet.FrameSize(size='foo.bar')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Frame size wrong type '
            '(expected int, got <type \'str\'>)')

        x = packet.FrameSize(size=50)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32')

    def test_raw_decode(self):
        x = packet.FrameSize()

        self.assertEquals(x.size, None)
        self.buffer.write('\x00\x00\x00\x32')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.size, 50)

    def test_encode(self):
        e = packet.FrameSize(size=2342)
        self.executed = False

        def cb(r):
            self.assertEquals(r, (1, '\x00\x00\t&'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.FrameSize))
            self.assertEquals(r.__dict__, {'size': 2342})
            self.executed = True

        d = packet.decode(1, '\x00\x00\t&').addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class ControlEventTestCase(BaseTestCase):
    """
    Tests for L{packet.ControlEvent}
    """

    def test_create(self):
        x = packet.ControlEvent()
        self.assertEquals(x.__dict__, {
            'type': None,
            'value1': 0,
            'value2': -1,
            'value3': -1
        })

        x = packet.ControlEvent(9, 123, 456, 789)
        self.assertEquals(x.__dict__, {
            'type': 9,
            'value1': 123,
            'value2': 456,
            'value3': 789
        })

        x = packet.ControlEvent(type=0, value1=123, value3=789, value2=456)
        self.assertEquals(x.__dict__, {
            'type': 0,
            'value1': 123,
            'value2': 456,
            'value3': 789
        })

    def test_raw_encode(self):
        x = packet.ControlEvent()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Unknown control type (type:None)')

        # test types ..
        x = packet.ControlEvent(type='3')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), "TypeError encoding type "
            "(expected int, got <type 'str'>)")

        x = packet.ControlEvent(type=3, value1=None)
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), "TypeError encoding value1 "
            "(expected int, got <type 'NoneType'>)")

        x = packet.ControlEvent(type=3, value1=10, value2=object())
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), "TypeError encoding value2 "
            "(expected int, got <type 'object'>)")

        x = packet.ControlEvent(type=3, value1=10, value2=7, value3='foo')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), "TypeError encoding value3 "
            "(expected int, got <type 'str'>)")

        self.buffer.truncate(0)
        x = packet.ControlEvent(2)
        e = x.encode(self.buffer)
        self.assertEquals(self.buffer.getvalue(),
            '\x00\x02\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff')

        self.buffer.truncate(0)
        x = packet.ControlEvent(type=0, value1=123, value3=789, value2=456)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(self.buffer.getvalue(),
            '\x00\x00\x00\x00\x00{\x00\x00\x01\xc8\x00\x00\x03\x15')

    def test_raw_decode(self):
        x = packet.ControlEvent()

        self.assertEquals(x.__dict__, {
            'type': None,
            'value1': 0,
            'value2': -1,
            'value3': -1
        })

        self.buffer.write('\x00\x00\x00\x00\x00{\x00\x00\x01\xc8\x00\x00\x03\x15')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.type, 0)
        self.assertEquals(x.value1, 123)
        self.assertEquals(x.value2, 456)
        self.assertEquals(x.value3, 789)

    def test_encode(self):
        e = packet.ControlEvent(9, 123, 456, 789)
        self.executed = False

        def cb(r):
            self.assertEquals(r, (4, '\x00\t\x00\x00\x00{\x00\x00\x01\xc8\x00'
                '\x00\x03\x15'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        bytes = '\x00\t\x00\x00\x00{\x00\x00\x01\xc8\x00\x00\x03\x15'
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.ControlEvent))
            self.assertEquals(r.__dict__, {
                'type': 9,
                'value1': 123,
                'value2': 456,
                'value3': 789})

            self.executed = True

        d = packet.decode(4, bytes).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_repr(self):
        e = packet.ControlEvent(9, 13, 45, 23)

        self.assertEquals(repr(e),
            '<ControlEvent type=9 value1=13 value2=45 value3=23 at 0x%x>' % (
                id(e)))


class NotifyTestCase(BaseTestCase):
    """
    Tests for L{packet.Notify}
    """

    def test_create(self):
        e = packet.Notify()
        self.assertEquals(e.__dict__, {'name': None, 'id': None, 'argv': {}})

        e = packet.Notify('foo', 'bar', baz='gak', spam='eggs')
        self.assertEquals(e.__dict__, {'name': 'foo', 'id': 'bar',
            'argv': {'baz': 'gak', 'spam': 'eggs'}})

    def test_repr(self):
        e = packet.Notify()
        self.assertEquals(repr(e),
            '<Notify name=None id=None argv={} at 0x%x>' % (id(e),))

        e = packet.Notify('foo', 'bar', baz='gak', spam='eggs')
        self.assertEquals(repr(e),
            "<Notify name='foo' id='bar' argv={'baz': 'gak', 'spam': 'eggs'} "
            "at 0x%x>" % (id(e),))

    def test_raw_encode(self):
        l = []
        e = packet.Notify()

        b1 = BufferedByteStream()
        d = e.encode(b1)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb(buf):
            self.assertEquals(buf, None)
            self.assertEquals(b1.getvalue(), '\x05\x05\x03\x00\x00\t')

        d.addCallback(cb)

        l.append(d)

        b2 = BufferedByteStream()
        d = e.encode(b2, encoding=pyamf.AMF3)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb2(buf):
            self.assertEquals(buf, None)
            self.assertEquals(b2.getvalue(), '\x01\x01\n\x0b\x01\x01')

        d.addCallback(cb2)

        l.append(d)

        return defer.DeferredList(l)

    def test_raw_decode(self):
        l = []
        e = packet.Notify()

        b1 = BufferedByteStream('\x05\x05\x03\x00\x00\t')
        d = e.decode(b1)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb(res):
            self.assertEquals(res, None)
            self.assertEquals(e.name, None)
            self.assertEquals(e.id, None)
            self.assertEquals(e.argv, {})

        d.addCallback(cb)

        l.append(d)

        b2 = BufferedByteStream('\x01\x01\n\x0b\x01\x01')
        d = e.decode(b2, encoding=pyamf.AMF3)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb2(res):
            self.assertEquals(res, None)
            self.assertEquals(e.name, None)
            self.assertEquals(e.id, None)
            self.assertEquals(e.argv, {})

        d.addCallback(cb2)

        l.append(d)

        return defer.DeferredList(l)

    def test_encode(self):
        e = packet.Notify('_result', 2, foo='bar', baz='gak')
        self.executed = False

        def cb(r):
            self.assertEquals(r, (18, '\x02\x00\x07_result\x00@\x00\x00\x00'
                '\x00\x00\x00\x00\x03\x00\x03foo\x02\x00\x03bar\x00\x03baz'
                '\x02\x00\x03gak\x00\x00\t'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        bytes = '\x02\x00\x07_result\x00@\x00\x00\x00\x00\x00\x00\x00\x03' + \
            '\x00\x03foo\x02\x00\x03bar\x00\x03baz\x02\x00\x03gak\x00\x00\t'
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.Notify))
            self.assertEquals(r.name, '_result')
            self.assertEquals(r.id, 2)
            self.assertEquals(r.argv, {'foo': 'bar', 'baz': 'gak'})

            self.executed = True

        d = packet.decode(18, bytes).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class InvokeTestCase(BaseTestCase):
    """
    Tests for L{packet.Invoke}
    """

    def test_create(self):
        e = packet.Invoke()
        self.assertEquals(e.__dict__, {'name': None, 'id': None, 'argv': {}})

        e = packet.Invoke('foo', 'bar', baz='gak', spam='eggs')
        self.assertEquals(e.__dict__, {'name': 'foo', 'id': 'bar',
            'argv': {'baz': 'gak', 'spam': 'eggs'}})

    def test_repr(self):
        e = packet.Invoke()
        self.assertEquals(repr(e),
            '<Invoke name=None id=None argv={} at 0x%x>' % (id(e),))

        e = packet.Invoke('foo', 'bar', baz='gak', spam='eggs')
        self.assertEquals(repr(e),
            "<Invoke name='foo' id='bar' argv={'baz': 'gak', 'spam': 'eggs'} "
            "at 0x%x>" % (id(e),))

    def test_raw_encode(self):
        l = []
        e = packet.Invoke()

        b1 = BufferedByteStream()
        d = e.encode(b1)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb(buf):
            self.assertEquals(buf, None)
            self.assertEquals(b1.getvalue(), '\x05\x05\x03\x00\x00\t')

        d.addCallback(cb)

        l.append(d)

        b2 = BufferedByteStream()
        d = e.encode(b2, encoding=pyamf.AMF3)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb2(buf):
            self.assertEquals(buf, None)
            self.assertEquals(b2.getvalue(), '\x01\x01\n\x0b\x01\x01')

        d.addCallback(cb2)

        l.append(d)

        return defer.DeferredList(l)

    def test_raw_decode(self):
        l = []
        e = packet.Invoke()

        b1 = BufferedByteStream('\x05\x05\x03\x00\x00\t')
        d = e.decode(b1)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb(res):
            self.assertEquals(res, None)
            self.assertEquals(e.name, None)
            self.assertEquals(e.id, None)
            self.assertEquals(e.argv, {})

        d.addCallback(cb)

        l.append(d)

        b2 = BufferedByteStream('\x01\x01\n\x0b\x01\x01')
        d = e.decode(b2, encoding=pyamf.AMF3)
        self.assertTrue(isinstance(d, defer.Deferred))

        def cb2(res):
            self.assertEquals(res, None)
            self.assertEquals(e.name, None)
            self.assertEquals(e.id, None)
            self.assertEquals(e.argv, {})

        d.addCallback(cb2)

        l.append(d)

        return defer.DeferredList(l)

    def test_encode(self):
        e = packet.Invoke('_result', 2, foo='bar', baz='gak')
        self.executed = False

        def cb(r):
            self.assertEquals(r, (20, '\x02\x00\x07_result\x00@\x00\x00\x00'
                '\x00\x00\x00\x00\x03\x00\x03foo\x02\x00\x03bar\x00\x03baz'
                '\x02\x00\x03gak\x00\x00\t'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        bytes = '\x02\x00\x07_result\x00@\x00\x00\x00\x00\x00\x00\x00\x03' + \
            '\x00\x03foo\x02\x00\x03bar\x00\x03baz\x02\x00\x03gak\x00\x00\t'
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.Invoke))
            self.assertEquals(r.name, '_result')
            self.assertEquals(r.id, 2)
            self.assertEquals(r.argv, {'foo': 'bar', 'baz': 'gak'})

            self.executed = True

        d = packet.decode(20, bytes).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class BytesReadTestCase(BaseTestCase):
    """
    Tests for L{packet.BytesRead}
    """

    def test_create(self):
        x = packet.BytesRead()
        self.assertEquals(x.__dict__, {'size': None})

        x = packet.BytesRead(10)
        self.assertEquals(x.__dict__, {'size': 10})

        x = packet.BytesRead(size=20)
        self.assertEquals(x.__dict__, {'size': 20})

    def test_raw_encode(self):
        # test default encode
        x = packet.BytesRead()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Bytes read not set')

        # test non-int encode
        x = packet.BytesRead(size='foo.bar')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Bytes read wrong type '
            '(expected int, got <type \'str\'>)')

        x = packet.BytesRead(size=50)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32')

    def test_raw_decode(self):
        x = packet.BytesRead()

        self.assertEquals(x.size, None)
        self.buffer.write('\x00\x00\x00\x32')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.size, 50)

    def test_encode(self):
        e = packet.BytesRead(size=2342)
        self.executed = False

        def cb(r):
            self.assertEquals(r, (3, '\x00\x00\t&'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.BytesRead))
            self.assertEquals(r.__dict__, {'size': 2342})
            self.executed = True

        d = packet.decode(3, '\x00\x00\t&').addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class ServerBandwidthTestCase(BaseTestCase):
    """
    Tests for L{packet.ServerBandwidth}
    """

    def test_create(self):
        x = packet.ServerBandwidth()
        self.assertEquals(x.__dict__, {'bandwidth': None})

        x = packet.ServerBandwidth(10)
        self.assertEquals(x.__dict__, {'bandwidth': 10})

        x = packet.ServerBandwidth(bandwidth=20)
        self.assertEquals(x.__dict__, {'bandwidth': 20})

    def test_raw_encode(self):
        # test default encode
        x = packet.ServerBandwidth()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Server bandwidth not set')

        # test non-int encode
        x = packet.ServerBandwidth(bandwidth='foo.bar')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Server bandwidth wrong type '
            '(expected int, got <type \'str\'>)')

        x = packet.ServerBandwidth(bandwidth=50)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32')

    def test_raw_decode(self):
        x = packet.ServerBandwidth()

        self.assertEquals(x.bandwidth, None)
        self.buffer.write('\x00\x00\x00\x32')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.bandwidth, 50)

    def test_encode(self):
        e = packet.ServerBandwidth(bandwidth=2342)
        self.executed = False

        def cb(r):
            self.assertEquals(r, (5, '\x00\x00\t&'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.ServerBandwidth))
            self.assertEquals(r.__dict__, {'bandwidth': 2342})
            self.executed = True

        d = packet.decode(5, '\x00\x00\t&').addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class ClientBandwidthTestCase(BaseTestCase):
    """
    Tests for L{packet.ClientBandwidth}
    """

    def test_create(self):
        x = packet.ClientBandwidth()
        self.assertEquals(x.__dict__, {'bandwidth': None, 'extra': None})

        x = packet.ClientBandwidth(10, 32)
        self.assertEquals(x.__dict__, {'bandwidth': 10, 'extra': 32})

        x = packet.ClientBandwidth(bandwidth=20, extra=233)
        self.assertEquals(x.__dict__, {'bandwidth': 20, 'extra': 233})

    def test_raw_encode(self):
        # test default encode
        x = packet.ClientBandwidth()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Client bandwidth not set')
        self.buffer.truncate(0)

        x = packet.ClientBandwidth(bandwidth='234')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Client extra not set')
        self.buffer.truncate(0)

        # test non-int encode
        x = packet.ClientBandwidth(bandwidth='foo.bar', extra=234)
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Client bandwidth wrong type '
            '(expected int, got <type \'str\'>)')
        self.buffer.truncate(0)

        # test non-int encode
        x = packet.ClientBandwidth(bandwidth=1200, extra='asdfas')
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Client extra wrong type '
            '(expected int, got <type \'str\'>)')
        self.buffer.truncate(0)

        x = packet.ClientBandwidth(bandwidth=50, extra=12)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32\x0C')

    def test_raw_decode(self):
        x = packet.ClientBandwidth()

        self.assertEquals(x.bandwidth, None)
        self.buffer.write('\x00\x00\x00\x32\x0C')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.bandwidth, 50)
        self.assertEquals(x.extra, 12)

    def test_encode(self):
        e = packet.ClientBandwidth(bandwidth=2342, extra=65)
        self.executed = False

        def cb(r):
            self.assertEquals(r, (6, '\x00\x00\t&A'))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.ClientBandwidth))
            self.assertEquals(r.__dict__, {'bandwidth': 2342, 'extra': 65})
            self.executed = True

        d = packet.decode(6, '\x00\x00\t&A').addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class AudioDataTestCase(BaseTestCase):
    """
    Tests for L{packet.AudioData}
    """

    def test_interface(self):
        self.assertTrue(interfaces.IStreamingPacket.implementedBy(packet.VideoData))

    def test_create(self):
        x = packet.AudioData()
        self.assertEquals(x.__dict__, {'data': None})

        x = packet.AudioData(10)
        self.assertEquals(x.__dict__, {'data': 10})

        x = packet.AudioData(data=20)
        self.assertEquals(x.__dict__, {'data': 20})

    def test_raw_encode(self):
        # test default encode
        x = packet.AudioData()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'No audio data set')

        # test non-str encode
        x = packet.AudioData(data=20)
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Audio data wrong type '
            '(expected str, got <type \'int\'>)')

        x = packet.AudioData(data='foo.bar')
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), 'foo.bar')

    def test_raw_decode(self):
        x = packet.AudioData()

        self.assertEquals(x.data, None)
        self.buffer.write('foo.bar')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.data, 'foo.bar')

    def test_encode(self):
        e = packet.AudioData(data=('abcdefg' * 50))
        self.executed = False

        def cb(r):
            self.assertEquals(r, (7, 'abcdefg' * 50))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.AudioData))
            self.assertEquals(r.__dict__, {'data': 'abcdefg' * 50})
            self.executed = True

        d = packet.decode(7, 'abcdefg' * 50).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d


class VideoDataTestCase(BaseTestCase):
    """
    Tests for L{packet.VideoData}
    """

    def test_interface(self):
        self.assertTrue(interfaces.IStreamingPacket.implementedBy(packet.VideoData))

    def test_create(self):
        x = packet.VideoData()
        self.assertEquals(x.__dict__, {'data': None})

        x = packet.VideoData(10)
        self.assertEquals(x.__dict__, {'data': 10})

        x = packet.VideoData(data=20)
        self.assertEquals(x.__dict__, {'data': 20})

    def test_raw_encode(self):
        # test default encode
        x = packet.VideoData()
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'No video data set')

        # test non-str encode
        x = packet.VideoData(data=20)
        e = self.assertRaises(packet.EncodeError, x.encode, self.buffer)
        self.assertEquals(str(e), 'Video data wrong type '
            '(expected str, got <type \'int\'>)')

        x = packet.VideoData(data='foo.bar')
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), 'foo.bar')

    def test_raw_decode(self):
        x = packet.VideoData()

        self.assertEquals(x.data, None)
        self.buffer.write('foo.bar')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.data, 'foo.bar')

    def test_encode(self):
        e = packet.VideoData(data=('abcdefg' * 50))
        self.executed = False

        def cb(r):
            self.assertEquals(r, (8, 'abcdefg' * 50))
            self.executed = True

        d = packet.encode(e).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d

    def test_decode(self):
        self.executed = False

        def cb(r):
            self.assertTrue(isinstance(r, packet.VideoData))
            self.assertEquals(r.__dict__, {'data': 'abcdefg' * 50})
            self.executed = True

        d = packet.decode(8, 'abcdefg' * 50).addCallback(cb)
        d.addCallback(lambda x: self.assertTrue(self.executed))
        d.addErrback(self._fail)

        return d
