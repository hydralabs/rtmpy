# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import defer

from rtmpy.tests import util
from rtmpy import rtmp, dispatcher
from rtmpy.util import BufferedByteStream as BBS

class ConstantsTestCase(unittest.TestCase):
    def test_all(self):
        self.assertEquals(rtmp.HEADER_SIZES, [12, 8, 4, 1])
        self.assertEquals(rtmp.HANDSHAKE_LENGTH, 1536)
        self.assertEquals(rtmp.HEADER_BYTE, '\x03')
        self.assertEquals(rtmp.HANDSHAKE_SUCCESS, 'rtmp.handshake.success')
        self.assertEquals(rtmp.HANDSHAKE_FAILURE, 'rtmp.handshake.failure')
        self.assertEquals(rtmp.HANDSHAKE_TIMEOUT, 'rtmp.handshake.timeout')
        self.assertEquals(rtmp.CHANNEL_COMPLETE, 'rtmp.channel.complete')


class ReadHeaderTestCase(unittest.TestCase):
    def test_12byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BBS('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.timer, '\x00\x00\x01')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)

    def test_8byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BBS('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)
        rtmp.read_header(channel, BBS('\x03\x02\x01\x01\x02\x03\x12'), 8)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.timer, '\x03\x02\x01')
        self.assertEquals(channel.type, 18)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)

    def test_4byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BBS('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)
        rtmp.read_header(channel, BBS('\x88\x77\x66'), 4)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.timer, '\x88\x77\x66')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)

    def test_1byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BBS('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)
        rtmp.read_header(channel, BBS(''), 1)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.timer, '\x00\x00\x01')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)


class HandshakeHelperTestCase(unittest.TestCase):
    def test_generate(self):
        # specify the uptime in ms
        hs = rtmp.generate_handshake(0, 0)

        self.assertEquals(hs[0:8], '\x00' * 8)
        self.assertEquals(len(hs), rtmp.HANDSHAKE_LENGTH)

        ms = 100000
        hs = rtmp.generate_handshake(ms, 50)
        self.assertEquals(hs[0:8], '\x00\x01\x86\xa0\x00\x00\x00\x32')
        self.assertEquals(len(hs), rtmp.HANDSHAKE_LENGTH)

    def test_decode(self):
        hs = rtmp.generate_handshake(0)
        uptime, ping, body = rtmp.decode_handshake(hs)

        self.assertEquals(uptime, 0)
        self.assertEquals(ping, 0)
        self.assertEquals(body, hs[8:])

        hs = rtmp.generate_handshake(100000, 345)
        uptime, ping, body = rtmp.decode_handshake(hs)

        self.assertEquals(uptime, 100000)
        self.assertEquals(ping, 345)
        self.assertEquals(body, hs[8:])


class RTMPChannelTestCase(unittest.TestCase):
    """
    Test for L{RTMPChannel}
    """

    def test_create(self):
        channel = rtmp.RTMPChannel(ord, 324)

        self.assertEquals(channel.protocol, ord)
        self.assertEquals(channel.channel_id, 324)
        self.assertEquals(channel.chunk_size, 128)
        self.assertEquals(channel.read, 0)
        self.assertEquals(channel.length, 0)
        self.assertTrue(isinstance(channel.body, BBS))

    def test_remaining(self):
        channel = rtmp.RTMPChannel(str, 0)
        channel.length = 1000

        self.assertEquals(channel.remaining, 1000)
        channel.read += 50

        self.assertEquals(channel.remaining, 950)

        channel.write('\x00' * 32)
        self.assertEquals(channel.remaining, 918)

    def test_write(self):
        channel = rtmp.RTMPChannel(str, 0)
        channel.length = 10

        self.assertEquals(channel.read, 0)
        channel.write('abc')
        self.assertEquals(channel.read, 3)

    def test_write_too_much(self):
        channel = rtmp.RTMPChannel(str, 0)
        channel.length = 2

        self.assertRaises(OverflowError, channel.write, 'abc')

    def test_write_complete(self):
        protocol = dispatcher.EventDispatcher()
        channel = rtmp.RTMPChannel(protocol, 0)
        channel.length = 2

        d = defer.Deferred()

        def complete(chan):
            self.assertIdentical(channel, chan)
            self.assertEquals(channel.body.tell(), 0)
            self.assertEquals(channel.body.getvalue(), '12')

            d.callback(None)

        protocol.addEventListener(rtmp.CHANNEL_COMPLETE, complete)
        channel.write('12')

        return d

    def test_write_no_complete_event(self):
        protocol = dispatcher.EventDispatcher()
        channel = rtmp.RTMPChannel(protocol, 0)
        channel.length = 2

        d = defer.Deferred()

        protocol.dispatchEvent = lambda _: self.fail("event dispatched")
        channel.write('2')

    def test_chunk_remaining(self):
        channel = rtmp.RTMPChannel(None, 0)

        channel.length = 280
        channel.chunk_size = 128
        channel.read = 0
        
        for x in xrange(128, 0, -1):
            self.assertEquals(channel.chunk_remaining, x)
            channel.read += 1

        self.assertEquals(channel.read, 128)

        for x in xrange(128, 0, -1):
            self.assertEquals(channel.chunk_remaining, x)
            channel.read += 1

        self.assertEquals(channel.read, 256)

        for x in xrange(24, 0, -1):
            self.assertEquals(channel.chunk_remaining, x)
            channel.read += 1

        self.assertEquals(channel.read, 280)

    def test_received_chunks(self):
        channel = rtmp.RTMPChannel(None, 0)

        channel.length = 280
        channel.chunk_size = 128

        channel.read = 0
        self.assertEquals(channel.chunks_received, 0)

        channel.read = 127
        self.assertEquals(channel.chunks_received, 0)

        channel.read = 128
        self.assertEquals(channel.chunks_received, 1)

        channel.read = 255
        self.assertEquals(channel.chunks_received, 1)

        channel.read = 256
        self.assertEquals(channel.chunks_received, 2)

        channel.read = 280
        self.assertEquals(channel.chunks_received, 3)

        channel = rtmp.RTMPChannel(None, 0)

        channel.length = 10
        channel.chunk_size = 128

        channel.read = 0
        self.assertEquals(channel.chunks_received, 0)

        channel.read = 9
        self.assertEquals(channel.chunks_received, 0)

        channel.read = 10
        self.assertEquals(channel.chunks_received, 1)


class HandshakeProtocolTestCase(unittest.TestCase):
    """
    Test for L{RTMPBaseProtocol} handshake phase
    """

    def test_timeout_handshake(self):
        p = rtmp.RTMPBaseProtocol()
        transport = util.StringTransport()
        d = defer.Deferred()

        def onTimeout():
            d.callback(None)

        p.addEventListener(rtmp.HANDSHAKE_TIMEOUT, onTimeout)
        p.handshakeTimeout = 0
        p.makeConnection(transport)

        return d

    def test_successful_handshake(self):
        p = rtmp.RTMPBaseProtocol()
        transport = util.StringTransport()
        d = defer.Deferred()
        self.removed_event = False

        p.makeConnection(transport)

        def remove_event(event, observerfn):
            if event == rtmp.HANDSHAKE_FAILURE and observerfn == p.onHandshakeFailure:
                self.removed_event = True

        def onHandshake():
            self.assertEquals(p.my_handshake, None)
            self.assertEquals(p.received_handshake, None)
            self.assertEquals(p.state, rtmp.RTMPBaseProtocol.STREAM)
            self.assertTrue(self.removed_event)
            self.assertEquals(p.buffer.getvalue(), '')

            d.callback(None)

        p.removeEventListener = remove_event
        p.addEventListener(rtmp.HANDSHAKE_SUCCESS, onHandshake)
        p.dispatchEvent(rtmp.HANDSHAKE_SUCCESS)

        return d

    def test_failed_handshake(self):
        p = rtmp.RTMPBaseProtocol()
        transport = util.StringTransportWithDisconnection()
        d = defer.Deferred()

        p.makeConnection(transport)
        transport.protocol = p

        def onEvent(reason):
            self.assertEquals(reason, None)
            self.assertFalse(transport.connected)

            d.callback(None)

        p.addEventListener(rtmp.HANDSHAKE_FAILURE, onEvent)

        self.assertTrue(transport.connected)
        p.dispatchEvent(rtmp.HANDSHAKE_FAILURE, None)

        return d


class BaseProtocolTestCase(unittest.TestCase):
    def test_make_connection(self):
        p = rtmp.RTMPBaseProtocol()
        transport = util.StringTransport()
        self.registered_success = self.registered_failure = False

        def check_observers(event, observerfn, priority=0, *args, **kwargs):
            if event == rtmp.HANDSHAKE_FAILURE:
                self.assertEquals(observerfn, p.onHandshakeFailure)
                self.registered_failure = True
            if event == rtmp.HANDSHAKE_SUCCESS:
                self.assertEquals(observerfn, p.onHandshakeSuccess)
                self.registered_success = True

        p.addEventListener = check_observers
        p.makeConnection(transport)
        p._timeout.cancel()

        self.assertEquals(p.channels, {})
        self.assertEquals(p.buffer.getvalue(), '')
        self.assertEquals(p.buffer.tell(), 0)
        self.assertEquals(p.state, rtmp.RTMPBaseProtocol.HANDSHAKE)
        self.assertEquals(p.my_handshake, None)
        self.assertEquals(p.received_handshake, None)
        self.assertTrue(self.registered_success)
        self.assertTrue(self.registered_failure)
        self.assertEquals(p.current_channel, None)

    def test_decode_handshake(self):
        p = rtmp.RTMPBaseProtocol()

        self.assertRaises(NotImplementedError, p.decodeHandshake)

    def test_send_data_handshake(self):
        self.executed = False

        def check():
            self.executed = True

        p = rtmp.RTMPBaseProtocol()
        p.makeConnection(util.StringTransport())
        p.decodeHandshake = check
        p.dataReceived('')
        p._timeout.cancel()

        self.assertTrue(self.executed)

    def test_lose_connection(self):
        self.executed = False

        p = rtmp.RTMPBaseProtocol()
        transport = util.StringTransport()

        p.makeConnection(transport)
        to = p._timeout

        def trunc():
            self.executed = True

        p.buffer.truncate = trunc
        p.connectionLost(None)

        self.assertFalse(hasattr(p, '_timeout'))
        self.assertTrue(to.cancelled)
        self.assertTrue(self.executed)


class ChannelManagementTestCase(unittest.TestCase):
    def setUp(self):
        self.protocol = rtmp.RTMPBaseProtocol()
        self.protocol.connectionMade()
        self.protocol._timeout.cancel()

        self.channels = self.protocol.channels

    def test_retrieve(self):
        self.assertRaises(IndexError, self.protocol.getChannel, -1)
        self.assertRaises(IndexError, self.protocol.getChannel, rtmp.MAX_CHANNELS)
        self.assertRaises(KeyError, self.protocol.getChannel, 0)

        x = object()
        self.channels[0] = x

        self.assertIdentical(self.protocol.getChannel(0), x)

    def test_create(self):
        self.assertRaises(IndexError, self.protocol.createChannel, -1)
        self.assertRaises(IndexError, self.protocol.createChannel, rtmp.MAX_CHANNELS)

        x = object()
        self.channels[0] = x

        self.assertRaises(KeyError, self.protocol.createChannel, 0)

        channel = self.protocol.createChannel(63)

        self.assertTrue(isinstance(channel, rtmp.RTMPChannel))
        self.assertEquals(channel.channel_id, 63)
        self.assertIdentical(channel.protocol, self.protocol)


class BaseRTMPParsingTestCase(unittest.TestCase):
    def setUp(self):
        self.protocol = rtmp.RTMPBaseProtocol()
        self.transport = util.StringTransportWithDisconnection()

        self.protocol.makeConnection(self.transport)
        self.transport.protocol = self.protocol
        self.buffer = self.protocol.buffer

        self.protocol._timeout.cancel()
        self.protocol.state = rtmp.RTMPBaseProtocol.STREAM


class RTMPParsingTestCase(BaseRTMPParsingTestCase):
    def test_receive_header_only(self):
        self.protocol.getChannel = lambda prot, channel_id: self.fail()

        self.protocol.dataReceived('\x00\x00\x00\x00')
        self.assertEquals(self.buffer.tell(), 4)
        self.assertEquals(self.protocol.current_channel, None)

    def test_single_channel_multiple_chunks(self):
        # 12 byte header
        for byte in '\x00\x00\x00\x00\x00\x01\x22\x14\x00\x00\x00\x00':
            self.protocol.dataReceived(byte)

        channel = self.protocol.channels[0]
        self.assertIdentical(self.protocol.current_channel, channel)

        # first 128 byte body
        for byte in '\x01' * 128:
            self.protocol.dataReceived(byte)

        self.assertIdentical(self.protocol.current_channel, None)
        self.assertEquals(channel.chunks_received, 1)
        self.assertEquals(channel.chunk_remaining, channel.chunk_size)
        self.assertEquals(channel.body.getvalue(), '\x01' * 128)

        # 1 byte header
        for byte in '\xc0':
            self.protocol.dataReceived(byte)

        self.assertIdentical(self.protocol.current_channel, channel)

        # second 128 byte body
        for byte in '\x02' * 128:
            self.protocol.dataReceived(byte)

        self.assertIdentical(self.protocol.current_channel, None)
        self.assertEquals(channel.chunks_received, 2)
        self.assertEquals(channel.chunk_remaining, 34)
        self.assertEquals(channel.body.getvalue(), '\x01' * 128 + '\x02' * 128)

        # 1 byte header
        for byte in '\xc0':
            self.protocol.dataReceived(byte)

        self.assertIdentical(self.protocol.current_channel, channel)

        # finaly 34 byte body
        for byte in '\x03' * 34:
            self.protocol.dataReceived(byte)

        self.assertIdentical(self.protocol.current_channel, None)
        self.assertEquals(channel.chunks_received, 3)
        self.assertEquals(channel.chunk_remaining, 0)
        self.assertEquals(channel.body.getvalue(),
            '\x01' * 128 + '\x02' * 128 + '\x03' * 34)

    def test_multiple_channel_multiple_chunks(self):
        # 12 byte header - channel 0
        for byte in '\x00\x00\x00\x00\x00\x00\x8a\x14\x00\x00\x00\x00':
            self.protocol.dataReceived(byte)

        channel0 = self.protocol.channels[0]
        self.assertIdentical(self.protocol.current_channel, channel0)

        # first 128 byte body
        for byte in '\x05' * 128:
            self.protocol.dataReceived(byte)

        self.assertEqual(channel0.body.getvalue(), '\x05' * 128)
        self.assertEqual(channel0.chunks_received, 1)
        self.assertEqual(channel0.chunk_remaining, 10)
        self.assertEqual(self.protocol.current_channel, None)

        # 12 byte header - channel 12 - body length = 34 base 10
        for byte in '\x0c\x00\x00\x00\x00\x00\x22\x14\x00\x00\x00\x00':
            self.protocol.dataReceived(byte)

        channel12 = self.protocol.channels[12]
        self.assertIdentical(self.protocol.current_channel, channel12)

        # channel 12 body
        for byte in '\x04' * 34:
            self.protocol.dataReceived(byte)

        self.assertEqual(channel12.body.getvalue(), '\x04' * 34)
        self.assertEqual(channel12.chunks_received, 1)
        self.assertEqual(channel12.chunk_remaining, 0)
        self.assertEqual(self.protocol.current_channel, None)

        # 1 byte header for channel 0
        for byte in '\xc0':
            self.protocol.dataReceived(byte)

        self.assertIdentical(self.protocol.current_channel, channel0)

        # second 10 byte body
        for byte in '\x05' * 10:
            self.protocol.dataReceived(byte)

        self.assertEquals(channel0.body.getvalue(), '\x05' * 138)
        self.assertEqual(channel0.chunks_received, 2)
        self.assertEqual(channel0.chunk_remaining, 0)
        self.assertEqual(self.protocol.current_channel, None)

    def test_receive_full_header(self):
        for byte in '\x00\x00\x00\x00\x00\x01\x8a\x14\x00\x00\x00\x00':
            self.protocol.dataReceived(byte)

        self.assertTrue(0 in self.protocol.channels)
        self.assertIdentical(self.protocol.channels[0], self.protocol.current_channel)

    def test_receive_full_chunk(self):
        channel = rtmp.RTMPChannel(self.protocol, 0)
        channel.length = 14

        self.protocol.channels[0] = channel
        self.protocol.current_channel = channel

        self.protocol.dataReceived('\x00' * 14)

        self.assertEquals(self.protocol.current_channel, None)
        self.assertEquals(self.protocol.buffer.remaining(), 0)

    def test_receive_multiple_chunks(self):
        channel = rtmp.RTMPChannel(self.protocol, 0)
        channel.length = 14 + channel.chunk_size

        self.protocol.channels[0] = channel
        self.protocol.current_channel = channel

        self.protocol.dataReceived('\x00' * channel.chunk_size)

        self.assertEquals(self.protocol.current_channel, None)
        self.assertEquals(self.protocol.buffer.remaining(), 0)

    def test_channel_complete(self):
        channel = rtmp.RTMPChannel(self.protocol, 0)
        channel.length = 14

        self.protocol.channels[0] = channel
        self.protocol.current_channel = channel
        d = defer.Deferred()

        def completeChannel(channel):
            self.assertFalse(0 in self.protocol.channels)
            d.callback(None)

        self.protocol.addEventListener(rtmp.CHANNEL_COMPLETE, completeChannel)
        self.protocol.dataReceived('\x00' * 14)

        return d

class ReadHeaderReplacingParsingTestCase(BaseRTMPParsingTestCase):
    def setUp(self):
        BaseRTMPParsingTestCase.setUp(self)
        self.read_header = rtmp.read_header

    def tearDown(self):
        BaseRTMPParsingTestCase.tearDown(self)
        rtmp.read_header = self.read_header

    def test_invalid_channel(self):
        rtmp.read_header = lambda a, b,c: self.fail("Function continued ..")

        def _getChannel(channel_id):
            raise IndexError

        self.protocol.getChannel = _getChannel
        self.to = self.protocol._timeout = util.DummyDelayedCall()

        self.protocol.dataReceived('\x00' + '\x00' * 12)
        self.assertFalse(self.transport.connected)

    def test_create_channel(self):        
        self.executed = False

        def run_checks(a, b, c):
            self.executed = True
            self.assertTrue(0 in self.protocol.channels.keys())
            channel = self.protocol.channels[0]

            self.assertTrue(isinstance(channel, rtmp.RTMPChannel))

        def create_channel(channel_id):
            self.assertEquals(channel_id, 0)

            return create_channel.orig_func(channel_id)

        create_channel.orig_func = self.protocol.createChannel
        self.protocol.createChannel = create_channel
        rtmp.read_header = run_checks

        self.protocol.dataReceived('\x00' + '\x00' * 12)

    def test_read_header(self):
        self.executed = False

        def read_header(a, b, c):
            self.executed = True
            self.assertEquals(a, self.protocol.channels[0])
            self.assertEquals(b, self.protocol.buffer)
            self.assertEquals(c, 12)

        rtmp.read_header = read_header

        self.protocol.dataReceived('\x00' + '\x00' * 12)
        self.assertTrue(self.executed)

    def test_write_to_channel(self):
        self.executed = False

        def check_chunk(length=None):
            self.executed = True
            self.assertEquals(length, 4)
            self.buffer.read = check_chunk.orig_func

            return check_chunk.orig_func(length)

        def read_header(a, b, c):
            self.read_header(a, b, c)
            self.channel = self.protocol.channels[0]
            check_chunk.orig_func = self.buffer.read
            self.buffer.read = check_chunk

        rtmp.read_header = read_header

        self.protocol.dataReceived('\x00\x00\x00\x00\x00\x00\x05\x14\x00' + \
            '\x00\x00\x00\x01\x02\x03\x04')

        self.assertTrue(self.executed)


class HeaderSizeDummy:
    def __init__(self, tc):
        self.tc = tc

    def __getitem__(self, item):
        self.tc.assertEquals(item, self.tc.expected_value)
        self.tc.executed = True

        return self.tc.header_sizes[item]


class RTMPHeaderLengthTestCase(BaseRTMPParsingTestCase):
    def setUp(self):
        BaseRTMPParsingTestCase.setUp(self)

        self.header_sizes = rtmp.HEADER_SIZES
        rtmp.HEADER_SIZES = HeaderSizeDummy(self)
        self.executed = False

    def tearDown(self):
        rtmp.HEADER_SIZES = self.header_sizes
        self.assertTrue(self.executed)

    def test_12bytes(self):
        self.expected_value = 0
        self.protocol.dataReceived('\x00')

    def test_8bytes(self):
        self.expected_value = 1
        self.protocol.dataReceived('\x40')

    def test_4bytes(self):
        self.expected_value = 2
        self.protocol.dataReceived('\x80')

    def test_1byte(self):
        self.expected_value = 3
        self.protocol.dataReceived('\xc0')
