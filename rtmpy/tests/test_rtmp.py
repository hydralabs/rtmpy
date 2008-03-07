# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import defer, reactor

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


class ReadHeaderTestCase(unittest.TestCase):
    def setUp(self):
        self.stream = BBS()
        self.header = rtmp.RTMPChannel(None, None, 0)

    def _write(self, bytes):
        self.stream.truncate()
        self.stream.write(bytes)
        self.stream.seek(0)

        rtmp.read_header(self.header, self.stream, len(bytes) + 1)

    def test_12byte_header(self):
        self._write('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        self.assertEquals(self.header.stream_id, 0)
        self.assertEquals(self.header.length, 261)
        self.assertEquals(self.header.timer, 1)
        self.assertEquals(self.header.type, 20)
        self.assertEquals(self.header.relative, False)

    def test_8byte_header(self):
        self._write('\x03\x02\x01\x01\x02\x03\x12')

        self.assertEquals(self.header.stream_id, None)
        self.assertEquals(self.header.length, 66051)
        self.assertEquals(self.header.timer, 197121)
        self.assertEquals(self.header.relative, True)
        self.assertEquals(self.header.type, 18)

    def test_4byte_header(self):
        self._write('\x88\x77\x66')

        self.assertEquals(self.header.stream_id, None)
        self.assertEquals(self.header.length, None)
        self.assertEquals(self.header.timer, 8943462)
        self.assertEquals(self.header.relative, True)
        self.assertEquals(self.header.type, None)

    def test_1byte_header(self):
        self._write('')

        self.assertEquals(self.header.stream_id, None)
        self.assertEquals(self.header.length, None)
        self.assertEquals(self.header.timer, None)
        self.assertEquals(self.header.relative, False)
        self.assertEquals(self.header.type, None)


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
        protocol = rtmp.RTMPBaseProtocol()
        manager = object()
        channel = rtmp.RTMPChannel(manager, protocol, 324)

        self.assertIdentical(channel.protocol, protocol)
        self.assertIdentical(channel.manager, manager)
        self.assertEquals(channel.channel_id, 324)
        self.assertEquals(channel.chunk_size, 128)
        self.assertEquals(channel.read, 0)
        self.assertEquals(channel.length, None)
        self.assertTrue(isinstance(channel.body, BBS))

    def test_remaining(self):
        channel = rtmp.RTMPChannel(object(), object(), 0)
        channel.length = 1000

        self.assertEquals(channel.remaining, 1000)
        channel.read += 50

        self.assertEquals(channel.remaining, 950)

        channel.write('\x00' * 32)
        self.assertEquals(channel.remaining, 918)

    def test_write(self):
        channel = rtmp.RTMPChannel(object(), object(), 0)
        channel.length = 10

        self.assertEquals(channel.read, 0)
        channel.write('abc')
        self.assertEquals(channel.read, 3)

    def test_write_too_much(self):
        channel = rtmp.RTMPChannel(object(), object(), 0)
        channel.length = 2

        self.assertRaises(OverflowError, channel.write, 'abc')

    def test_write_complete(self):
        protocol = dispatcher.EventDispatcher()
        channel = rtmp.RTMPChannel(protocol, object(), 0)
        channel.length = 2

        d = defer.Deferred()

        def complete(chan):
            try:
                self.assertIdentical(channel, chan)
                self.assertEquals(channel.body.tell(), 0)
                self.assertEquals(channel.body.getvalue(), '12')
            except:
                d.errback()
            else:
                d.callback(None)

        protocol.addEventListener(rtmp.ChannelManager.CHANNEL_COMPLETE, complete)
        channel.write('12')

        return d

    def test_write_no_complete_event(self):
        protocol = dispatcher.EventDispatcher()
        channel = rtmp.RTMPChannel(protocol, object(), 0)
        channel.length = 2

        d = defer.Deferred()

        protocol.dispatchEvent = lambda _: self.fail("event dispatched")
        channel.write('2')

    def test_chunk_remaining(self):
        channel = rtmp.RTMPChannel(object(), object(), 0)

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
        channel = rtmp.RTMPChannel(object(), object(), 0)

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

        channel = rtmp.RTMPChannel(object(), object(), 0)

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
            try:
                self.assertEquals(p.my_handshake, None)
                self.assertEquals(p.received_handshake, None)
                self.assertEquals(p.state, rtmp.RTMPBaseProtocol.STREAM)
                self.assertTrue(self.removed_event)
                self.assertEquals(p.buffer.getvalue(), '')
                self.assertTrue(isinstance(p.channel_manager, rtmp.ChannelManager))
                self.assertEquals(p.current_channel, None)
            except:
                d.errback()
            else:
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

        self.assertEquals(p.buffer.getvalue(), '')
        self.assertEquals(p.buffer.tell(), 0)
        self.assertEquals(p.state, rtmp.RTMPBaseProtocol.HANDSHAKE)
        self.assertEquals(p.my_handshake, None)
        self.assertEquals(p.received_handshake, None)
        self.assertTrue(self.registered_success)
        self.assertTrue(self.registered_failure)

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

    def test_set_timeout(self):
        p = rtmp.RTMPBaseProtocol()
        d = defer.Deferred()
        p.setTimeout(0, lambda: d.callback(None))

        return d

    def test_clear_timeout(self):
        p = rtmp.RTMPBaseProtocol()
        p.clearTimeout()

        self.assertFalse(hasattr(p, '_timeout'))

        p = rtmp.RTMPBaseProtocol()
        p._timeout = reactor.callLater(0, lambda: None)
        p.clearTimeout()

        self.assertFalse(hasattr(p, '_timeout'))


class ChannelManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.protocol = object()
        self.manager = rtmp.ChannelManager(self.protocol)

    def test_retrieve(self):
        self.assertRaises(IndexError, self.manager.getChannel, -1)
        self.assertRaises(IndexError, self.manager.getChannel, rtmp.MAX_CHANNELS)
        self.assertRaises(KeyError, self.manager.getChannel, 0)

        x = object()
        self.manager._channels[0] = x

        self.assertIdentical(self.manager.getChannel(0), x)

    def test_init(self):
        manager = rtmp.ChannelManager(self.protocol)
        
        self.assertIdentical(self.protocol, manager.protocol)
        self.assertEquals(manager._channels, {})
        self.assertEquals(manager.max_channels, rtmp.MAX_CHANNELS)
        self.assertTrue(manager.hasEventListener(rtmp.ChannelManager.CHANNEL_COMPLETE))

        # check max_channels
        max_channels = 3
        self.assertTrue(max_channels < rtmp.MAX_CHANNELS)
        manager = rtmp.ChannelManager(self.protocol, max_channels)
        self.assertEquals(manager.max_channels, max_channels)

        # check max_channels > 0
        max_channels = 0
        self.assertRaises(ValueError, rtmp.ChannelManager, self.protocol, max_channels)

        # check max_channels < rtmp.MAX_CHANNELS
        max_channels = 0xffff
        self.assertTrue(max_channels > rtmp.MAX_CHANNELS)
        manager = rtmp.ChannelManager(self.protocol, max_channels)
        self.assertEquals(manager.max_channels, rtmp.MAX_CHANNELS)

    def test_create(self):
        self.manager._channels = {}

        # automatically create channel
        channel = self.manager.createChannel()

        self.assertTrue(channel in self.manager._channels.values())
        self.assertEquals(self.manager._channels, {0: channel})

        self.assertRaises(IndexError, self.manager.createChannel, -1)
        self.assertRaises(IndexError, self.manager.createChannel, rtmp.MAX_CHANNELS)

        self.manager._channels = {45: 'foo'}
        self.assertRaises(KeyError, self.manager.createChannel, 45)

        self.manager._channels = {2: 'bar'}
        channel = self.manager.createChannel(12)

        self.assertTrue(isinstance(channel, rtmp.RTMPChannel))
        self.assertEquals(channel.manager, self.manager)

    def test_next_channel_id(self):
        self.assertEquals(self.manager.getNextChannelId(), 0)

        self.manager._channels = {0: None, 1: True, 2: False}
        self.assertEquals(self.manager.getNextChannelId(), 3)

        self.manager._channels = {0: None, 2: False}
        self.assertEquals(self.manager.getNextChannelId(), 1)

        self.manager._channels = {}
        for x in range(rtmp.MAX_CHANNELS):
            self.manager._channels[x] = None

        self.assertRaises(OverflowError, self.manager.getNextChannelId)

    def test_remove(self):
        self.assertRaises(KeyError, self.manager.removeChannel, 0)
        self.manager._channels[0] = True

        self.manager.removeChannel(0)
        self.assertEquals(self.manager._channels, {})

        self.assertRaises(IndexError, self.manager.removeChannel, -1)
        self.assertRaises(IndexError, self.manager.removeChannel, rtmp.MAX_CHANNELS)

    def test_fire_complete(self):
        d = defer.Deferred()
        channel = rtmp.RTMPChannel(self.manager, self.protocol, 0)

        def cb(ch):
            try:
                self.assertIdentical(ch, channel)
            except:
                d.errback()
            else:
                d.callback(None)

        self.manager.removeEventListener(rtmp.ChannelManager.CHANNEL_COMPLETE, self.manager.onCompleteBody)
        self.manager.addEventListener(rtmp.ChannelManager.CHANNEL_COMPLETE, cb)
        self.manager.dispatchEvent(rtmp.ChannelManager.CHANNEL_COMPLETE, channel)
        
        return d

    def test_complete(self):
        channel = rtmp.RTMPChannel(self.manager, self.protocol, 0)
        self.manager._channels[0] = channel

        self.manager.onCompleteBody(channel)

        self.assertFalse(channel in self.manager._channels.values())
        self.assertRaises(KeyError, self.manager.onCompleteBody, channel)


class StreamManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.protocol = object()
        self.manager = rtmp.StreamManager(self.protocol)

    def test_retrieve(self):
        self.assertRaises(IndexError, self.manager.getStream, -1)
        self.assertRaises(IndexError, self.manager.getStream, rtmp.MAX_STREAMS)
        self.assertRaises(KeyError, self.manager.getStream, 0)

        x = object()
        self.manager._streams[0] = x
        self.manager._rev_streams[x] = 0

        self.assertIdentical(self.manager.getStream(0), x)

    def test_init(self):
        manager = rtmp.StreamManager(self.protocol)
        
        self.assertIdentical(self.protocol, manager.protocol)
        self.assertEquals(manager._streams, {})
        self.assertEquals(manager._rev_streams, {})
        self.assertEquals(manager.max_streams, rtmp.MAX_STREAMS)

        # check max_channels
        max_streams = 3
        self.assertTrue(max_streams < rtmp.MAX_STREAMS)
        manager = rtmp.StreamManager(self.protocol, max_streams)
        self.assertEquals(manager.max_streams, max_streams)

        # check max_streams > 0
        max_streams = 0
        self.assertRaises(ValueError, rtmp.StreamManager, self.protocol, max_streams)

        # check max_streams < rtmp.MAX_STREAMS
        manager = rtmp.StreamManager(self.protocol, rtmp.MAX_STREAMS + 1)
        self.assertEquals(manager.max_streams, rtmp.MAX_STREAMS)

    def test_create(self):
        self.manager._streams = {}
        self.manager._rev_streams = {}

        # automatically create channel
        stream = self.manager.createStream()

        self.assertTrue(stream in self.manager._streams.values())
        self.assertEquals(self.manager._streams, {0: stream})
        self.assertEquals(self.manager._rev_streams, {stream: 0})

        self.assertRaises(IndexError, self.manager.createStream, -1)
        self.assertRaises(IndexError, self.manager.createStream, rtmp.MAX_STREAMS)

        self.manager._streams = {45: 'foo'}
        self.manager._rev_streams = {'foo': 45}
        self.assertRaises(KeyError, self.manager.createStream, 45)

        self.manager._streams = {2: 'bar'}
        self.manager._rev_streams = {'bar': 2}
        stream = self.manager.createStream(12)

        self.assertTrue(isinstance(stream, rtmp.RTMPStream))
        self.assertEquals(stream.manager, self.manager)

    def test_next_stream_id(self):
        self.assertEquals(self.manager.getNextStreamId(), 0)

        self.manager._streams = {0: None, 1: True, 2: False}
        self.assertEquals(self.manager.getNextStreamId(), 3)

        self.manager._streams = {0: None, 2: False}
        self.assertEquals(self.manager.getNextStreamId(), 1)

        self.manager._streams = {}
        for x in range(rtmp.MAX_STREAMS):
            self.manager._streams[x] = None

        self.assertRaises(OverflowError, self.manager.getNextStreamId)

    def test_remove(self):
        self.assertRaises(KeyError, self.manager.removeStream, 0)
        self.manager._streams[0] = True
        self.manager._rev_streams[True] = 0

        self.manager.removeStream(0)
        self.assertEquals(self.manager._streams, {})
        self.assertEquals(self.manager._rev_streams, {})

        self.assertRaises(IndexError, self.manager.removeStream, -1)
        self.assertRaises(IndexError, self.manager.removeStream, rtmp.MAX_STREAMS)


class BaseRTMPParsingTestCase(unittest.TestCase):
    def setUp(self):
        self.protocol = rtmp.RTMPBaseProtocol()
        self.transport = util.StringTransportWithDisconnection()

        self.protocol.makeConnection(self.transport)
        self.transport.protocol = self.protocol
        self.buffer = self.protocol.buffer

        self.protocol._timeout.cancel()
        self.protocol.state = rtmp.RTMPBaseProtocol.STREAM
        self.protocol.onHandshakeSuccess()

        self.channel_manager = self.protocol.channel_manager
        self.stream_manager = self.protocol.stream_manager


class RTMPParsingTestCase(BaseRTMPParsingTestCase):
    def _write(self, bytes):
        self.protocol.dataReceived(bytes)
        self.protocol.decodeStream()

    def test_receive_header_only(self):
        self.protocol.getChannel = lambda prot, channel_id: self.fail()

        self.protocol.dataReceived('\x00\x00\x00\x00')
        self.assertEquals(self.buffer.tell(), 4)
        self.assertEquals(self.protocol.current_channel, None)

    def test_single_channel_multiple_chunks(self):
        # 12 byte header
        self._write('\x00\x00\x00\x00\x00\x01\x22\x14\x00\x00\x00\x00')

        channel = self.channel_manager.getChannel(0)
        self.assertIdentical(self.protocol.current_channel, channel)

        # first 128 byte body
        self._write('\x01' * 128)

        self.assertIdentical(self.protocol.current_channel, None)
        self.assertEquals(channel.chunks_received, 1)
        self.assertEquals(channel.chunk_remaining, channel.chunk_size)
        self.assertEquals(channel.body.getvalue(), '\x01' * 128)

        # 1 byte header
        self._write('\xc0')

        self.assertIdentical(self.protocol.current_channel, channel)

        # second 128 byte body
        self._write('\x02' * 128)

        self.assertIdentical(self.protocol.current_channel, None)
        self.assertEquals(channel.chunks_received, 2)
        self.assertEquals(channel.chunk_remaining, 34)
        self.assertEquals(channel.body.getvalue(), '\x01' * 128 + '\x02' * 128)

        # 1 byte header
        self._write('\xc0')

        self.assertIdentical(self.protocol.current_channel, channel)

        # finaly 34 byte body
        self._write('\x03' * 34)

        self.assertIdentical(self.protocol.current_channel, None)
        self.assertEquals(channel.chunks_received, 3)
        self.assertEquals(channel.chunk_remaining, 0)
        self.assertEquals(channel.body.getvalue(),
            '\x01' * 128 + '\x02' * 128 + '\x03' * 34)

    def test_multiple_channel_multiple_chunks(self):
        # 12 byte header - channel 0
        self._write('\x00\x00\x00\x00\x00\x00\x8a\x14\x00\x00\x00\x00')
        channel0 = self.channel_manager.getChannel(0)
        self.assertIdentical(self.protocol.current_channel, channel0)

        # first 128 byte body
        self._write('\x05' * 128)
        self.assertEqual(channel0.body.getvalue(), '\x05' * 128)
        self.assertEqual(channel0.chunks_received, 1)
        self.assertEqual(channel0.chunk_remaining, 10)
        self.assertEqual(self.protocol.current_channel, None)

        # 12 byte header - channel 12 - body length = 34
        self._write('\x0c\x00\x00\x00\x00\x00\x22\x14\x00\x00\x00\x00')

        channel12 = self.channel_manager.getChannel(12)
        self.assertIdentical(self.protocol.current_channel, channel12)

        # channel 12 body
        self._write('\x04' * 34)
        self.assertEqual(channel12.body.getvalue(), '\x04' * 34)
        self.assertEqual(channel12.chunks_received, 1)
        self.assertEqual(channel12.chunk_remaining, 0)
        self.assertEqual(self.protocol.current_channel, None)

        # 1 byte header for channel 0
        self._write('\xc0')
        self.assertIdentical(self.protocol.current_channel, channel0)

        # second 10 byte body
        self._write('\x05' * 10)
        self.assertEquals(channel0.body.getvalue(), '\x05' * 138)
        self.assertEqual(channel0.chunks_received, 2)
        self.assertEqual(channel0.chunk_remaining, 0)
        self.assertEqual(self.protocol.current_channel, None)

    def test_receive_full_header(self):
        self._write('\x00\x00\x00\x00\x00\x01\x8a\x14\x00\x00\x00\x00')
        channel = self.channel_manager.getChannel(0)
        self.assertIdentical(channel, self.protocol.current_channel)

    def test_receive_full_chunk(self):
        channel = rtmp.RTMPChannel(self.channel_manager, self.protocol, 0)
        channel.length = 14

        self.channel_manager._channels[0] = channel
        self.protocol.current_channel = channel

        self.protocol.dataReceived('\x00' * 14)

        self.assertEquals(self.protocol.current_channel, None)
        self.assertEquals(self.protocol.buffer.remaining(), 0)

    def test_receive_multiple_chunks(self):
        channel = rtmp.RTMPChannel(self.channel_manager, self.protocol, 0)
        channel.length = 14 + channel.chunk_size

        self.channel_manager._channels[0] = channel
        self.protocol.current_channel = channel

        self.protocol.dataReceived('\x00' * channel.chunk_size)

        self.assertEquals(self.protocol.current_channel, None)
        self.assertEquals(self.protocol.buffer.remaining(), 0)

    def test_channel_complete(self):
        channel = rtmp.RTMPChannel(self.channel_manager, self.protocol, 0)
        channel.length = 14

        self.channel_manager._channels[0] = channel
        self.protocol.current_channel = channel
        
        d = defer.Deferred()

        def completeChannel(channel):
            try:
                self.assertRaises(KeyError, self.channel_manager.getChannel, 0)
                self.assertEquals(self.protocol.current_channel, None)
            except:
                d.errback()
            else:
                d.callback(None)

        self.channel_manager.addEventListener(rtmp.ChannelManager.CHANNEL_COMPLETE, completeChannel)
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
        rtmp.read_header = lambda *args: self.fail("Function continued ..")

        def _getChannel(channel_id):
            raise IndexError

        self.protocol.getChannel = _getChannel
        self.to = self.protocol._timeout = util.DummyDelayedCall()

        self.protocol.dataReceived('\x00' + '\x00' * 12)
        self.assertFalse(self.transport.connected)

    def test_create_channel(self):
        d = defer.Deferred()

        def run_checks(*args):
            try:
                channel = self.channel_manager.getChannel(0)

                self.assertTrue(isinstance(channel, rtmp.RTMPChannel))
            except:
                d.errback()
            else:
                d.callback(None)

        def create_channel(channel_id):
            try:
                self.assertEquals(channel_id, 0)

                return create_channel.orig_func(channel_id)
            except:
                d.errback()
            else:
                d.callback(None)

        create_channel.orig_func = self.channel_manager.createChannel
        self.channel_manager.createChannel = create_channel
        rtmp.read_header = run_checks

        self.protocol.dataReceived('\x00' + '\x00' * 12)

        return d

    def test_read_header(self):
        self.executed = False

        def read_header(*args):
            self.executed = True
            self.assertEquals(a, self.protocol.channels[0])
            self.assertEquals(b, self.protocol.buffer)
            self.assertEquals(c, 12)

        rtmp.read_header = read_header

        self.protocol.dataReceived('\x00' + '\x00' * 12)
        self.assertTrue(self.executed)

    def test_write_to_channel(self):
        d = defer.Deferred()

        def check_chunk(data=None):
            try:
                self.assertEquals(data, '\x01\x02\x03\x04')
                self.channel.write = check_chunk.orig_func
            except:
                d.errback()
            else:
                d.callback(None)

                return check_chunk.orig_func(length)

        def read_header(*args):
            try:
                self.read_header(*args)
                self.channel = self.channel_manager.getChannel(0)
                check_chunk.orig_func = self.channel.write
                self.channel.write = check_chunk
            except:
                d.errback()

        rtmp.read_header = read_header

        self.protocol.dataReceived('\x00\x00\x00\x00\x00\x00\x05\x14\x00' + \
            '\x00\x00\x00\x01\x02\x03\x04')

        return d


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
