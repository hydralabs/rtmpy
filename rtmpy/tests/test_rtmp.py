# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.protocol}
"""

from twisted.trial import unittest
from twisted.internet import defer

from rtmpy.tests import util
from rtmpy import rtmp

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
        pass


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

        p.addOnetimeObserver = check_observers
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

        p.removeObserver = remove_event
        p.addObserver(rtmp.HANDSHAKE_SUCCESS, onHandshake)
        p.dispatch(rtmp.HANDSHAKE_SUCCESS)

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

        p.addObserver(rtmp.HANDSHAKE_FAILURE, onEvent)

        self.assertTrue(transport.connected)
        p.dispatch(rtmp.HANDSHAKE_FAILURE, None)

        return d

    def test_read_full_header(self):
        p = rtmp.RTMPBaseProtocol()

        p.makeConnection(util.StringTransport())
        p.state = rtmp.RTMPBaseProtocol.STREAM

        p.dataReceived('\x03\x00\x00\x01\x00\x01\x05\x14\x00\x00\x00\x00')

        self.assertTrue(3 in p.channels)
        channel = p.channels[3]

        self.assertEquals(channel.unknown, '\x00\x00\x01')
        self.assertEquals(channel.type, 20)
        self.assertEquals(channel.channel_id, 3)
        self.assertEquals(channel.protocol, p)
