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
Tests for L{rtmpy.protocol.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import error, defer, reactor
from twisted.test.proto_helpers import StringTransportWithDisconnection

from rtmpy.protocol import rtmp
from rtmpy.protocol.rtmp import message, status
from rtmpy import exc


class MockHandshakeNegotiator(object):
    """
    """

    def __init__(self, test, protocol):
        self.test = test
        self.procotol = protocol
        self.started = False

        self.data = None

    def start(self, uptime, version):
        self.started = True

    def dataReceived(self, data):
        if self.data is None:
            self.data = data
        else:
            self.data += data


class MockFactory(object):
    """
    """

    def __init__(self, test, protocol):
        self.test = test
        self.protocol = protocol

    def buildHandshakeNegotiator(self, protocol):
        self.test.assertIdentical(protocol, self.protocol)

        return self.test.handshaker


class MockApplication(object):
    """
    """

    def __init__(self, test, protocol):
        self.test = test
        self.protocol = protocol

    def clientDisconnected(self, client, reason):
        self.test.assertIdentical(client, self.protocol)


class ProtocolTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.protocol = rtmp.RTMPProtocol()
        self.handshaker = MockHandshakeNegotiator(self, self.protocol)
        self.transport = self.protocol.transport = StringTransportWithDisconnection()
        self.transport.protocol = self.protocol

    def connect(self):
        self.protocol.factory = MockFactory(self, self.protocol)
        self.protocol.connectionMade()


class StateTest(ProtocolTestCase):
    """
    Test protocol state between not connected/handshaking/streaming/disconnected
    """

    def test_not_connected(self):
        self.assertFalse(hasattr(self.protocol, 'state'))

    def test_connect(self):
        self.connect()

        self.assertEqual(self.protocol.state, 'handshake')
        self.assertTrue(self.handshaker.started)

        self.assertIdentical(self.protocol.handshaker, self.handshaker)

    def test_stream(self):
        self.connect()
        self.protocol.handshakeSuccess('')

        self.assertEqual(self.protocol.state, 'stream')
        self.assertFalse(hasattr(self.protocol, 'handshaker'))
        self.assertEqual(self.protocol.streams, {0: self.protocol})


class ConnectionLostTestCase(ProtocolTestCase):
    """
    Tests for losing connection at various states of the protocol
    """

    def setUp(self):
        ProtocolTestCase.setUp(self)

        self.connect()

    def test_handshake(self):
        self.protocol.connectionLost(error.ConnectionDone())

        self.assertFalse(hasattr(self.protocol, 'handshaker'))

    def test_stream(self):
        self.protocol.handshakeSuccess('')

        self.protocol.connectionLost(error.ConnectionDone())

        self.assertFalse(hasattr(self.protocol, 'decoder'))
        self.assertFalse(hasattr(self.protocol, 'encoder'))

    def test_decode_task(self):
        self.protocol.handshakeSuccess('')
        self.protocol._startDecoding()

        self.assertTrue(hasattr(self.protocol, 'decoder_task'))
        self.protocol.connectionLost(error.ConnectionDone())
        self.assertFalse(hasattr(self.protocol, 'decoder_task'))

    def test_encode_task(self):
        self.protocol.handshakeSuccess('')
        self.protocol._startEncoding()

        self.assertTrue(hasattr(self.protocol, 'encoder_task'))
        self.protocol.connectionLost(error.ConnectionDone())
        self.assertFalse(hasattr(self.protocol, 'encoder_task'))

    def test_inform_application(self):
        self.protocol.handshakeSuccess('')
        self.protocol.application = MockApplication(self, self.protocol)

        self.protocol.connectionLost(error.ConnectionDone())



class TestRuntimeError(RuntimeError):
    pass



class CooperateTestCase(ProtocolTestCase):
    """
    Tests for encoding/decoding cooperation
    """

    def setUp(self):
        ProtocolTestCase.setUp(self)

        self.connect()
        self.protocol.handshakeSuccess('')

    def test_fail_decode(self):
        """
        If something goes wrong whilst decoding, ensure that protocol disconnects
        """
        def boom(*args):
            raise TestRuntimeError

        self.patch(self.protocol.decoder, 'next', boom)

        def eb(f):
            f.trap(TestRuntimeError)

            self.assertFalse(self.transport.connected)
            self.flushLoggedErrors(TestRuntimeError)

        d = self.protocol._startDecoding().addErrback(eb)

        return d

    def test_fail_encode(self):
        def boom(*args):
            raise TestRuntimeError

        self.patch(self.protocol.encoder, 'next', boom)

        def eb(f):
            f.trap(TestRuntimeError)

            self.assertFalse(self.transport.connected)
            self.flushLoggedErrors(TestRuntimeError)

        d = self.protocol._startEncoding().addErrback(eb)

        return d

    def test_resume_decode(self):
        d = self.protocol._startDecoding()

        def resume(res):
            self.assertTrue(self.transport.connected)
            return self.protocol._startDecoding()

        d.addCallback(resume)

        return d


class DataReceivedTestCase(ProtocolTestCase):
    """
    """

    def test_handshake(self):
        self.connect()
        self.assertEqual(self.protocol.state, 'handshake')

        self.protocol.dataReceived('woot')
        self.assertEqual(self.handshaker.data, 'woot')

        self.protocol.dataReceived('slartybartfarst')
        self.assertEqual(self.handshaker.data, 'wootslartybartfarst')

    def test_stream(self):
        self.connect()
        self.protocol.handshakeSuccess('')

        decoder = self.protocol.decoder

        self.assertEqual(self.protocol.decoder_task, None)
        self.protocol.dataReceived('woot')
        self.assertNotEqual(self.protocol.decoder_task, None)

        self.assertEqual(decoder.stream.getvalue(), 'woot')

        self.protocol.decoder_task.addErrback(lambda x: None)


class StreamTestCase(ProtocolTestCase):
    """
    Tests for L{rtmp.Stream}
    """

    def setUp(self):
        ProtocolTestCase.setUp(self)

        self.stream = rtmp.NetStream(self.protocol, None)

    def test_create(self):
        """
        Ensure basic attribute initialisation and constructor args.
        """
        s = rtmp.NetStream(self.protocol, 3)

        self.assertEqual(s.streamId, 3)
        self.assertEqual(s.timestamp, 0)

    def test_set_timestamp(self):
        """
        @see: L{rtmp.Stream.setTimestamp}
        """
        self.assertEqual(self.stream.timestamp, 0)

        self.stream.setTimestamp(50)
        self.assertEqual(self.stream.timestamp, 50)

        self.stream.setTimestamp(50)
        self.assertEqual(self.stream.timestamp, 100)

        self.stream.setTimestamp(150, False)
        self.assertEqual(self.stream.timestamp, 150)

    def test_send_message(self):
        """
        Send a message back to the protocol.
        """
        self.executed = False

        def send_message(message, whenDone, stream=None):
            self.assertIdentical(self.stream, stream)
            self.assertEqual(message, 'foo')
            self.assertEqual(whenDone, 'bar')

            self.executed = True

        self.patch(self.protocol, 'sendMessage', send_message)

        self.stream.sendMessage('foo', 'bar')
        self.assertTrue(self.executed)


class BasicResponseTestCase(ProtocolTestCase):
    """
    Some RTMP messages are really low level. Test them.
    """

    def setUp(self):
        ProtocolTestCase.setUp(self)

        self.factory = MockFactory(self, self.protocol)
        self.protocol.factory = self.factory

        self.protocol.connectionMade()
        self.protocol.handshakeSuccess('')

        self.decoder = self.protocol.decoder

        self.messages = []

        def send_message(*args, **kwargs):
            args = list(args) + [kwargs.get('stream', None)]
            self.messages.append(args)

        self.patch(self.protocol, 'sendMessage', send_message)

        self.stream = self.protocol.streams[self.protocol.createStream()]

    def test_send_bytes_read(self):
        """
        Tests to ensure that the bytes read keep alive packet is dispatched
        correctly.
        """
        self.decoder.setBytesInterval(8)
        self.decoder.send('\x03\x00\x00\x00\x00\x00\x04\x01\x00\x00\x00\x00'
            '\x00\x00\x00\x32')

        self.decoder.next()

        self.assertEqual(len(self.messages), 1)

        msg, _, = self.messages[0]

        self.assertEqual(_, None)
        self.assertIsInstance(msg, message.BytesRead)
        self.assertEqual(msg.bytes, 16)

    def test_frame_size(self):
        """
        When a L{message.FrameSize} message is received, ensure that the decoder
        is updated correctly.
        """
        self.decoder.send('\x03\x00\x00\x00\x00\x00\x04\x01\x00\x00\x00\x00'
            '\x00\x00\x00\x32')

        self.assertNotEqual(self.decoder.frameSize, 50)

        [x for x in self.decoder]

        self.assertEqual(self.decoder.frameSize, 50)
        self.assertEqual(self.messages, [])

    def test_sendStatus(self):
        self.stream.sendStatus('blarg', 'foo', description='spam', one=1, two='two')

        msg, whenDone, stream = self.messages.pop(0)

        self.assertEqual(self.messages, [])
        self.assertIdentical(stream, self.stream)
        self.assertEqual(whenDone, None)

        self.assertIsInstance(msg, message.Invoke)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'onStatus')

        s = status.Status('status', 'blarg', description='spam', one=1, two='two')
        self.assertEqual(msg.argv, ['foo', s])

    def test_send_status_no_args(self):
        """
        If not supplied, the resulting L{message.Invoke} should result in
        C{argv=[None, <status.Status ...}
        """
        self.stream.sendStatus('spam', description='eggs')

        msg, whenDone, stream = self.messages.pop(0)

        self.assertEqual(self.messages, [])
        self.assertIdentical(stream, self.stream)
        self.assertEqual(whenDone, None)

        self.assertIsInstance(msg, message.Invoke)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'onStatus')

        s = status.Status('status', 'spam', description='eggs')
        self.assertEqual(msg.argv, [None, s])

    def test_send_status_instance(self):
        """
        Sending a L{status.Status} instance should allow sending other types of
        status messages (e.g. level='error')
        """
        s = status.Status('error', 'spam', description='eggs')

        self.stream.sendStatus(s)

        msg, whenDone, stream = self.messages.pop(0)

        self.assertEqual(self.messages, [])
        self.assertIdentical(stream, self.stream)
        self.assertEqual(whenDone, None)

        self.assertIsInstance(msg, message.Invoke)
        self.assertEqual(msg.id, 0)
        self.assertEqual(msg.name, 'onStatus')

        self.assertEqual(msg.argv, [None, s])


class InvokableStream(rtmp.NetStream):
    """
    Be able to control the targets easily.
    """

    targets = {}

    def getInvokableTarget(self, name):
        return self.targets.get(name, None)


class InvokingTestCase(ProtocolTestCase):
    """
    """

    def setUp(self):
        ProtocolTestCase.setUp(self)

        self.factory = MockFactory(self, self.protocol)
        self.protocol.factory = self.factory

        self.protocol.connectionMade()
        self.protocol.handshakeSuccess('')

        self.decoder = self.protocol.decoder

        self.messages = []

        def send_message(*args, **kwargs):
            args = list(args) + [kwargs.get('stream', None)]
            self.messages.append(args)

        self.patch(self.protocol, 'sendMessage', send_message)

        self.targets = {}
        self.stream = InvokableStream(self.protocol, 3)
        self.stream.targets = self.targets

    def test_init(self):
        """
        Stream creation defaults.
        """
        self.assertEqual(self.stream.activeInvokes, {})
        self.assertEqual(self.stream.lastInvokeId, -1)

    def test_reset(self):
        """
        Stream reset defaults.
        """
        self.stream.activeInvokes = 'woo'
        self.stream.lastInvokeId = 'blarg'

        self.stream.reset()

        self.assertEqual(self.stream.activeInvokes, {})
        self.assertEqual(self.stream.lastInvokeId, -1)

    def test_missing_target(self):
        """
        Invoke a method that does not exist with no response expected.
        """
        self.assertEqual(self.stream.getInvokableTarget('foo'), None)

        d = self.stream.onInvoke('foo', 0, [], 0)

        self.assertIsInstance(d, defer.Deferred)

        def cb(res):
            self.fail('errback should be called')

        def eb(fail):
            fail.trap(exc.CallFailed)

            self.assertEqual(fail.getErrorMessage(), "Unknown method 'foo'")

        def check_messages(res):
            self.assertEqual(self.messages, [])

        d.addCallbacks(cb, eb).addCallback(check_messages)

        return d

    def test_missing_target_response(self):
        """
        Invoke a method that does not exist with a response expected.
        """
        self.assertEqual(self.stream.getInvokableTarget('foo'), None)

        d = self.stream.onInvoke('foo', 1, [], 0)

        self.assertIsInstance(d, defer.Deferred)

        def cb(res):
            self.fail('errback should be called')

        def eb(fail):
            fail.trap(exc.CallFailed)

            self.assertEqual(fail.getErrorMessage(), "Unknown method 'foo'")

        def check_messages(res):
            msg, whenDone, stream = self.messages.pop(0)

            self.assertEqual(self.messages, [])

            self.assertEqual(whenDone, None)
            self.assertIdentical(stream, self.stream)

            self.assertIsInstance(msg, message.Invoke)
            self.assertEqual(msg.id, 1)
            self.assertEqual(msg.name, '_error')
            self.assertEqual(msg.argv, [None, {
                'code': 'NetConnection.Call.Failed',
                'description': "Unknown method 'foo'",
                'level': 'error'}])

        d.addCallbacks(cb, eb).addCallback(check_messages)

        return d

    def test_success_response(self):
        """
        Test a successful invocation with a response.
        """
        def func():
            return 'bar'

        self.targets['foo'] = func

        self.assertEqual(self.stream.getInvokableTarget('foo'), func)

        d = self.stream.onInvoke('foo', 1, [], 0)
        self.assertIsInstance(d, defer.Deferred)

        def check_messages(res):
            msg, whenDone, stream = self.messages.pop(0)

            self.assertEqual(self.messages, [])

            self.assertEqual(whenDone, None)
            self.assertIdentical(stream, self.stream)

            self.assertIsInstance(msg, message.Invoke)
            self.assertEqual(msg.id, 1)
            self.assertEqual(msg.name, '_result')
            self.assertEqual(msg.argv, [None, 'bar'])

        d.addCallback(check_messages)

        return d

    def test_failure_response(self):
        """
        Test a successful invocation but that raises an error.
        """
        def func():
            raise RuntimeError('spam and eggs please')

        self.targets['foo'] = func

        self.assertEqual(self.stream.getInvokableTarget('foo'), func)

        d = self.stream.onInvoke('foo', 1, [], 0)
        self.assertIsInstance(d, defer.Deferred)

        def eb(fail):
            fail.trap(RuntimeError)

        def check_messages(res):
            msg, whenDone, stream = self.messages.pop(0)

            self.assertEqual(self.messages, [])

            self.assertEqual(whenDone, None)
            self.assertIdentical(stream, self.stream)

            self.assertIsInstance(msg, message.Invoke)
            self.assertEqual(msg.id, 1)
            self.assertEqual(msg.name, '_error')
            self.assertEqual(msg.argv, [None, {
                'code': 'NetConnection.Call.Failed',
                'description': 'spam and eggs please',
                'level': 'error'}])

        d.addErrback(eb).addCallback(check_messages)

        return d

    def test_args(self):
        """
        Pass args to the target
        """
        def func(a, b, c):
            self.assertEqual(a, 'foo')
            self.assertEqual(b, 'bar')
            self.assertEqual(c, 'baz')

        self.targets['foo'] = func

        self.assertEqual(self.stream.getInvokableTarget('foo'), func)

        d = self.stream.onInvoke('foo', 1, ['foo', 'bar', 'baz'], 0)
        self.assertIsInstance(d, defer.Deferred)

        def check_messages(res):
            self.assertNotEqual(self.messages, [])

        d.addCallback(check_messages)

        return d

    def test_deferred(self):
        """
        Await the response of a deferred
        """
        wait_ok = defer.Deferred()
        my_deferred = defer.Deferred()

        def check_messages(res):
            msg, whenDone, stream = self.messages.pop(0)

            self.assertEqual(self.messages, [])

            self.assertEqual(whenDone, None)
            self.assertIdentical(stream, self.stream)

            self.assertIsInstance(msg, message.Invoke)
            self.assertEqual(msg.id, 1)
            self.assertEqual(msg.name, '_result')
            self.assertEqual(msg.argv, [None, 'foo'])

        def wrap_ok(res):
            try:
                check_messages(res)
            except:
                wait_ok.errback()
            else:
                wait_ok.callback(res)

        def func():
            def join():
                my_deferred.callback('foo')
                reactor.callLater(0, my_deferred.addCallback, wrap_ok)

            reactor.callLater(0, join)

            return my_deferred

        self.targets['foo'] = func

        self.assertEqual(self.stream.getInvokableTarget('foo'), func)

        d = self.stream.onInvoke('foo', 1, [], 0)
        self.assertIsInstance(d, defer.Deferred)

        return wait_ok

    def test_missing_active(self):
        my_deferred = defer.Deferred()

        def func():
            reactor.callLater(0, my_deferred.callback, None)

            return my_deferred

        self.targets['foo'] = func

        self.assertEqual(self.stream.getInvokableTarget('foo'), func)

        d = self.stream.onInvoke('foo', 1, [], 0)
        self.stream.activeInvokes = {}
        self.assertIsInstance(d, defer.Deferred)

        def eb(fail):
            fail.trap(RuntimeError)

        def check_messages(res):
            msg, whenDone, stream = self.messages.pop(0)

            self.assertEqual(self.messages, [])

            self.assertEqual(whenDone, None)
            self.assertIdentical(stream, self.stream)

            self.assertIsInstance(msg, message.Invoke)
            self.assertEqual(msg.id, 1)
            self.assertEqual(msg.name, '_error')
            self.assertEqual(msg.argv, [None, {}])

        my_deferred.addErrback(eb).addCallback(check_messages)

        return d
