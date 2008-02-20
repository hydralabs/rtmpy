# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp}
"""

from twisted.trial import unittest
from twisted.internet import defer

from rtmpy.tests import util
from rtmpy import rtmp
from rtmpy.util import BufferedByteStream

class ConstTestCase(unittest.TestCase):
    def test_all(self):
        self.assertEquals(rtmp.HANDSHAKE_LENGTH, 1536)
        self.assertEquals(rtmp.HEADER_BYTE, '\x03')


class HandshakeHelperTestCase(unittest.TestCase):
    def test_generate(self):
        # specify the uptime in ms
        hs = rtmp.generate_handshake(0)

        self.assertEquals(hs[0:8], '\x00' * 8)
        self.assertEquals(len(hs), rtmp.HANDSHAKE_LENGTH)

        ms = 100000
        hs = rtmp.generate_handshake(ms)
        self.assertEquals(hs[0:8], '\x00\x01\x86\xa0\x00\x00\x00\x00')
        self.assertEquals(len(hs), rtmp.HANDSHAKE_LENGTH)

    def test_decode(self):
        hs = rtmp.generate_handshake(0)
        uptime, body = rtmp.decode_handshake(hs)

        self.assertEquals(uptime, 0)
        self.assertEquals(body, hs[4:])

        hs = rtmp.generate_handshake(100000)
        uptime, body = rtmp.decode_handshake(hs)

        self.assertEquals(uptime, 100000)
        self.assertEquals(body, hs[4:])


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


class ReadHeaderTestCase(unittest.TestCase):
    def test_12byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BufferedByteStream('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.unknown, '\x00\x00\x01')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)

    def test_8byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BufferedByteStream('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)
        rtmp.read_header(channel, BufferedByteStream('\x03\x02\x01\x01\x02\x03\x12'), 8)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.unknown, '\x03\x02\x01')
        self.assertEquals(channel.type, 18)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)

    def test_4byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BufferedByteStream('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)
        rtmp.read_header(channel, BufferedByteStream('\x88\x77\x66'), 4)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.unknown, '\x88\x77\x66')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)

    def test_1byte_header(self):
        channel = rtmp.RTMPChannel(None, 0)
        stream = BufferedByteStream('\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        rtmp.read_header(channel, stream, 12)
        rtmp.read_header(channel, BufferedByteStream(''), 1)

        self.assertEquals(channel.destination, 0)
        self.assertEquals(channel.unknown, '\x00\x00\x01')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 0)
        self.assertEquals(channel.protocol, None)


class BaseProtocolTestCase(unittest.TestCase):
    """
    Test for L{RTMPProtocol}
    """

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

        self.assertEquals(p.channels, {})
        self.assertEquals(p.buffer.getvalue(), '')
        self.assertEquals(p.buffer.tell(), 0)
        self.assertEquals(p.state, rtmp.RTMPBaseProtocol.HANDSHAKE)
        self.assertEquals(p.my_handshake, None)
        self.assertEquals(p.received_handshake, None)
        self.assertTrue(self.registered_success)
        self.assertTrue(self.registered_failure)

    def test_successful_handshake(self):
        p = rtmp.RTMPBaseProtocol()
        transport = util.StringTransport()
        d = defer.Deferred()
        self.removed_event = False
        transport.write('blah')

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

    def test_consume_buffer(self):
        p = rtmp.RTMPBaseProtocol()
        p.connectionMade()
        stream = p.buffer

        stream.write('abcdefg')
        stream.seek(2)
        p._consumeBuffer()
        self.assertEquals(stream.getvalue(), 'cdefg')
        self.assertEquals(stream.tell(), 0)

        stream.seek(2)
        p._consumeBuffer()
        self.assertEquals(stream.getvalue(), 'efg')
        self.assertEquals(stream.tell(), 0)

        stream.seek(0, 2)
        p._consumeBuffer()
        self.assertEquals(stream.getvalue(), '')
        self.assertEquals(stream.tell(), 0)
