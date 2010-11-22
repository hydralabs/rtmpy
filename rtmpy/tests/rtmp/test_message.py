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
Tests for L{rtmpy.protocol.rtmp.message}.
"""

import unittest
from pyamf.util import BufferedByteStream

from rtmpy.protocol.rtmp import message


class MockMessageListener(object):
    """
    """

    def __init__(self):
        self.calls = []

    def onInvoke(self, *args, **kwargs):
        self.calls.append(('invoke', args, kwargs))

    def onNotify(self, *args, **kwargs):
        self.calls.append(('notify', args, kwargs))

    def onFrameSize(self, *args, **kwargs):
        self.calls.append(('frame-size', args, kwargs))

    def onBytesRead(self, *args, **kwargs):
        self.calls.append(('bytes-read', args, kwargs))

    def onControlMessage(self, *args, **kwargs):
        self.calls.append(('control', args, kwargs))

    def onDownstreamBandwidth(self, *args, **kwargs):
        self.calls.append(('bw-down', args, kwargs))

    def onUpstreamBandwidth(self, *args, **kwargs):
        self.calls.append(('bw-up', args, kwargs))

    def onAudioData(self, *args, **kwargs):
        self.calls.append(('audio', args, kwargs))

    def onVideoData(self, *args, **kwargs):
        self.calls.append(('video', args, kwargs))


class BaseTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.buffer = BufferedByteStream()
        self.listener = MockMessageListener()


class MessageTestCase(unittest.TestCase):
    """
    Tests for L{message.Message}
    """

    def test_interface(self):
        x = message.Message()

        self.assertTrue(message.IMessage.providedBy(x))

        self.assertRaises(NotImplementedError, x.encode, None)
        self.assertRaises(NotImplementedError, x.decode, None)
        self.assertRaises(NotImplementedError, x.dispatch, None, None)

    def test_repr(self):
        x = message.Message()
        x.foo = 'bar'

        self.assertEqual(repr(x),
            "<rtmpy.protocol.rtmp.message.Message foo='bar' at 0x%x>" % id(x))


class FrameSizeTestCase(BaseTestCase):
    """
    Tests for L{message.FrameSize}
    """

    def test_create(self):
        x = message.FrameSize()
        self.assertEquals(x.__dict__, {'size': None})

        x = message.FrameSize(10)
        self.assertEquals(x.__dict__, {'size': 10})

        x = message.FrameSize(size=20)
        self.assertEquals(x.__dict__, {'size': 20})

    def test_raw_encode(self):
        # test default encode
        x = message.FrameSize()
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Frame size not set')

        # test non-int encode
        x = message.FrameSize(size='foo.bar')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Frame size wrong type '
        #    '(expected int, got <type \'str\'>)')

        x = message.FrameSize(size=50)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32')

    def test_decode(self):
        x = message.FrameSize()

        self.assertEquals(x.size, None)
        self.buffer.write('\x00\x00\x00\x32')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.size, 50)

    def test_dispatch(self):
        x = message.FrameSize(5678)

        x.dispatch(self.listener, 54)

        self.assertEquals(self.listener.calls, [('frame-size', (5678, 54), {})])


class ControlMessageTestCase(BaseTestCase):
    """
    Tests for L{message.ControlMessage}
    """

    def test_create(self):
        x = message.ControlMessage()
        self.assertEquals(x.__dict__, {
            'type': None,
            'value1': 0,
            'value2': None,
            'value3': None
        })

        x = message.ControlMessage(9, 123, 456, 789)
        self.assertEquals(x.__dict__, {
            'type': 9,
            'value1': 123,
            'value2': 456,
            'value3': 789
        })

        x = message.ControlMessage(type=0, value1=123, value3=789, value2=456)
        self.assertEquals(x.__dict__, {
            'type': 0,
            'value1': 123,
            'value2': 456,
            'value3': 789
        })

    def test_encode(self):
        x = message.ControlMessage()
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Type not set')

        # test types ..
        x = message.ControlMessage(type='3')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError encoding type "
        #    "(expected int, got <type 'str'>)")

        x = message.ControlMessage(type=3, value1=None)
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError encoding value1 "
        #    "(expected int, got <type 'NoneType'>)")

        x = message.ControlMessage(type=3, value1=10, value2=object())
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError encoding value2 "
        #    "(expected int, got <type 'object'>)")

        x = message.ControlMessage(type=3, value1=10, value2=7, value3='foo')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError encoding value3 "
        #    "(expected int, got <type 'str'>)")

        self.buffer.truncate(0)
        x = message.ControlMessage(2)
        e = x.encode(self.buffer)
        #self.assertEquals(self.buffer.getvalue(),
        #    '\x00\x02\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff')

        self.buffer.truncate(0)
        x = message.ControlMessage(type=0, value1=123, value3=789, value2=456)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(self.buffer.getvalue(),
            '\x00\x00\x00\x00\x00{\x00\x00\x01\xc8\x00\x00\x03\x15')

    def test_decode(self):
        x = message.ControlMessage()

        self.assertEquals(x.__dict__, {
            'type': None,
            'value1': 0,
            'value2': None,
            'value3': None
        })

        self.buffer.write('\x00\x00\x00\x00\x00{\x00\x00\x01\xc8\x00\x00\x03\x15')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.type, 0)
        self.assertEquals(x.value1, 123)
        self.assertEquals(x.value2, 456)
        self.assertEquals(x.value3, 789)

    def test_dispatch(self):
        x = message.ControlMessage()

        x.dispatch(self.listener, 54)

        self.assertEquals(self.listener.calls, [('control', (x, 54), {})])


class NotifyTestCase(BaseTestCase):
    """
    Tests for L{message.Notify}
    """

    def test_create(self):
        e = message.Notify()
        self.assertEquals(e.__dict__, {'name': None, 'argv': []})

        e = message.Notify('foo', {'baz': 'gak', 'spam': 'eggs'}, 'yar')
        self.assertEquals(e.__dict__, {'name': 'foo',
            'argv': [{'baz': 'gak', 'spam': 'eggs'}, 'yar']})

    def test_encode(self):
        e = message.Notify('_result', 2, {'foo': 'bar', 'baz': 'gak'})

        e.encode(self.buffer)

        self.assertEqual(self.buffer.getvalue(), '\x02\x00\x07_result\x00@\x00'
            '\x00\x00\x00\x00\x00\x00\x03\x00\x03foo\x02\x00\x03bar\x00\x03baz'
            '\x02\x00\x03gak\x00\x00\t')

    def test_decode_simple(self):
        e = message.Notify()

        self.buffer.append('\x05\x03\x00\x00\t')
        e.decode(self.buffer)

        self.assertEquals(e.name, None)
        self.assertEquals(e.argv, [{}])


    def test_decode(self):
        e = message.Notify()

        self.buffer.append('\x02\x00\x07_result\x03\x00\x03foo\x02\x00\x03bar'
            '\x00\x03baz\x02\x00\x03gak\x00\x00\t')

        e.decode(self.buffer)

        self.assertEquals(e.name, '_result')
        self.assertEquals(e.argv, [{'foo': 'bar', 'baz': 'gak'}])

    def test_dispatch(self):
        x = message.Notify('foo')

        x.dispatch(self.listener, 54)
        self.assertEquals(self.listener.calls, [('notify', ('foo', [], 54), {})])


class InvokeTestCase(BaseTestCase):
    """
    Tests for L{message.Invoke}
    """

    def test_create(self):
        e = message.Invoke()
        self.assertEquals(e.__dict__, {'name': None, 'id': None, 'argv': []})

        e = message.Invoke('foo', 'bar', {'baz': 'gak', 'spam': 'eggs'}, 'yar')
        self.assertEquals(e.__dict__, {'name': 'foo', 'id': 'bar',
            'argv': [{'baz': 'gak', 'spam': 'eggs'}, 'yar']})

    def test_encode(self):
        e = message.Invoke('_result', 2, {'foo': 'bar', 'baz': 'gak'})

        e.encode(self.buffer)

        self.assertEqual(self.buffer.getvalue(), '\x02\x00\x07_result\x00@\x00'
            '\x00\x00\x00\x00\x00\x00\x03\x00\x03foo\x02\x00\x03bar\x00\x03baz'
            '\x02\x00\x03gak\x00\x00\t')

    def test_decode_simple(self):
        e = message.Invoke()

        self.buffer.append('\x05\x05\x03\x00\x00\t')
        e.decode(self.buffer)

        self.assertEquals(e.name, None)
        self.assertEquals(e.id, None)
        self.assertEquals(e.argv, [{}])


    def test_decode(self):
        e = message.Invoke()

        self.buffer.append('\x02\x00\x07_result\x00@\x00\x00\x00\x00\x00\x00'
            '\x00\x03\x00\x03foo\x02\x00\x03bar\x00\x03baz\x02\x00\x03gak\x00'
            '\x00\t')

        e.decode(self.buffer)

        self.assertEquals(e.name, '_result')
        self.assertEquals(e.id, 2)
        self.assertEquals(e.argv, [{'foo': 'bar', 'baz': 'gak'}])

    def test_dispatch(self):
        x = message.Invoke()

        x.dispatch(self.listener, 54)
        self.assertEquals(self.listener.calls,
            [('invoke', (None, None, [], 54), {})])


class BytesReadTestCase(BaseTestCase):
    """
    Tests for L{message.BytesRead}
    """

    def test_create(self):
        x = message.BytesRead()
        self.assertEquals(x.__dict__, {'bytes': None})

        x = message.BytesRead(10)
        self.assertEquals(x.__dict__, {'bytes': 10})

        x = message.BytesRead(bytes=20)
        self.assertEquals(x.__dict__, {'bytes': 20})


    def test_encode(self):
        # test default encode
        x = message.BytesRead()
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Bytes read not set')

        # test non-int encode
        x = message.BytesRead(bytes='foo.bar')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Bytes read wrong type '
        #    '(expected int, got <type \'str\'>)')

        x = message.BytesRead(bytes=50)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32')


    def test_4GB_threshold(self):
        """
        Test wrapping when encoding byte values > 4GB.

        @see: #54
        """
        x = message.BytesRead(bytes=message.BytesRead.FOUR_GB_THRESHOLD)

        x.encode(self.buffer)

        self.assertEqual(self.buffer.getvalue(), '\x00\x00\x00\x00')


    def test_decode(self):
        x = message.BytesRead()

        self.assertEquals(x.bytes, None)
        self.buffer.write('\x00\x00\x00\x32')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.bytes, 50)

    def test_dispatch(self):
        x = message.BytesRead(90)

        x.dispatch(self.listener, 54)

        self.assertEquals(self.listener.calls, [('bytes-read', (90, 54), {})])


class DownstreamBandwidthTestCase(BaseTestCase):
    """
    Tests for L{message.DownstreamBandwidth}
    """

    def test_create(self):
        x = message.DownstreamBandwidth()
        self.assertEquals(x.__dict__, {'bandwidth': None})

        x = message.DownstreamBandwidth(10)
        self.assertEquals(x.__dict__, {'bandwidth': 10})

        x = message.DownstreamBandwidth(bandwidth=20)
        self.assertEquals(x.__dict__, {'bandwidth': 20})

    def test_encode(self):
        # test default encode
        x = message.DownstreamBandwidth()
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Downstream bandwidth not set')

        # test non-int encode
        x = message.DownstreamBandwidth(bandwidth='foo.bar')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError for downstream bandwidth "
        #    "(expected int, got <type 'str'>)")

        x = message.DownstreamBandwidth(bandwidth=50)
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32')

    def test_decode(self):
        x = message.DownstreamBandwidth()

        self.assertEquals(x.bandwidth, None)
        self.buffer.write('\x00\x00\x00\x32')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.bandwidth, 50)

    def test_dispatch(self):
        x = message.DownstreamBandwidth('foo')

        x.dispatch(self.listener, 54)

        self.assertEquals(self.listener.calls, [('bw-down', ('foo', 54), {})])


class UpstreamBandwidthTestCase(BaseTestCase):
    """
    Tests for L{message.UpstreamBandwidth}
    """

    def test_create(self):
        x = message.UpstreamBandwidth()
        self.assertEquals(x.__dict__, {'bandwidth': None, 'extra': None})

        x = message.UpstreamBandwidth(10, 32)
        self.assertEquals(x.__dict__, {'bandwidth': 10, 'extra': 32})

        x = message.UpstreamBandwidth(bandwidth=20, extra=233)
        self.assertEquals(x.__dict__, {'bandwidth': 20, 'extra': 233})

    def test_encode(self):
        # test default encode
        x = message.UpstreamBandwidth()
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Upstream bandwidth not set')
        self.buffer.truncate(0)

        x = message.UpstreamBandwidth(bandwidth='234')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'Extra not set')
        self.buffer.truncate(0)

        # test non-int encode
        x = message.UpstreamBandwidth(bandwidth='foo.bar', extra=234)
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError: Upstream bandwidth "
        #    "(expected int, got <type 'str'>)")
        self.buffer.truncate(0)

        # test non-int encode
        x = message.UpstreamBandwidth(bandwidth=1200, extra='asdfas')
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError: extra "
        #    "(expected int, got <type 'str'>)")
        self.buffer.truncate(0)

        x = message.UpstreamBandwidth(bandwidth=50, extra=12)
        x.encode(self.buffer)

        self.assertEquals(self.buffer.getvalue(), '\x00\x00\x00\x32\x0C')

    def test_decode(self):
        x = message.UpstreamBandwidth()

        self.assertEquals(x.bandwidth, None)
        self.buffer.write('\x00\x00\x00\x32\x0C')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.bandwidth, 50)
        self.assertEquals(x.extra, 12)

    def test_dispatch(self):
        x = message.UpstreamBandwidth('foo', 'bar')

        x.dispatch(self.listener, 54)
        self.assertEquals(self.listener.calls, [('bw-up', ('foo', 'bar', 54), {})])


class AudioDataTestCase(BaseTestCase):
    """
    Tests for L{message.AudioData}
    """

    def test_streaming(self):
        self.assertTrue(message.AUDIO_DATA in message.STREAMABLE_TYPES)

    def test_create(self):
        x = message.AudioData()
        self.assertEquals(x.__dict__, {'data': None})

        x = message.AudioData(10)
        self.assertEquals(x.__dict__, {'data': 10})

        x = message.AudioData(data=20)
        self.assertEquals(x.__dict__, {'data': 20})

    def test_encode(self):
        # test default encode
        x = message.AudioData()
        self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'No data set')

        # test non-str encode
        x = message.AudioData(data=20)
        self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError: data "
        #    "(expected str, got <type 'int'>)")

        x = message.AudioData(data='foo.bar')
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), 'foo.bar')

    def test_decode(self):
        x = message.AudioData()

        self.assertEquals(x.data, None)
        self.buffer.write('foo.bar')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.data, 'foo.bar')

    def test_dispatch(self):
        x = message.AudioData('foo')

        x.dispatch(self.listener, 54)

        self.assertEquals(self.listener.calls, [('audio', ('foo', 54), {})])


class VideoDataTestCase(BaseTestCase):
    """
    Tests for L{message.VideoData}
    """

    def test_streaming(self):
        self.assertTrue(message.VIDEO_DATA in message.STREAMABLE_TYPES)

    def test_create(self):
        x = message.VideoData()
        self.assertEquals(x.__dict__, {'data': None})

        x = message.VideoData(10)
        self.assertEquals(x.__dict__, {'data': 10})

        x = message.VideoData(data=20)
        self.assertEquals(x.__dict__, {'data': 20})

    def test_encode(self):
        # test default encode
        x = message.VideoData()
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), 'No data set')

        # test non-str encode
        x = message.VideoData(data=20)
        e = self.assertRaises(message.EncodeError, x.encode, self.buffer)
        #self.assertEquals(str(e), "TypeError: data "
        #    "(expected str, got <type 'int'>)")

        x = message.VideoData(data='foo.bar')
        e = x.encode(self.buffer)

        self.assertEquals(e, None)

        self.assertEquals(self.buffer.getvalue(), 'foo.bar')

    def test_raw_decode(self):
        x = message.VideoData()

        self.assertEquals(x.data, None)
        self.buffer.write('foo.bar')
        self.buffer.seek(0)

        e = x.decode(self.buffer)

        self.assertEquals(e, None)
        self.assertEquals(x.data, 'foo.bar')

    def test_dispatch(self):
        x = message.VideoData('foo')

        x.dispatch(self.listener, 54)

        self.assertEquals(self.listener.calls, [('video', ('foo', 54), {})])


class HelperTestCase(unittest.TestCase):
    def test_type_class(self):
        for k, v in message.TYPE_MAP.iteritems():
            self.assertEquals(message.get_type_class(k), v)

        self.assertFalse('foo' in message.TYPE_MAP.keys())
        self.assertRaises(message.UnknownEventType, message.get_type_class, 'foo')
