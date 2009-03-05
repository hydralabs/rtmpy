# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE.txt for details.

"""
Encoding tests for L{rtmpy.rtmp.codec}.
"""

from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy import util
from rtmpy.tests.util import DummyChannelManager, DummyChannel, DummyHeader


class BaseEncoderTestCase(unittest.TestCase):
    """
    """

    def setUp(self):
        self.manager = DummyChannelManager()
        self.encoder = codec.Encoder(self.manager)
        self.buffer = util.BufferedByteStream()

        self.encoder.registerConsumer(self.buffer)


class ClassContextTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.ChannelContext}.
    """

    def setUp(self):
        BaseEncoderTestCase.setUp(self)

        self.channel = DummyChannel()
        self.context = codec.ChannelContext(self.channel, self.encoder)
        self.buffer = self.context.buffer

    def test_init(self):
        self.assertIdentical(self.context.channel, self.channel)
        self.assertIdentical(self.context.encoder, self.encoder)

        self.assertTrue(isinstance(self.context.buffer, util.BufferedByteStream))
        self.assertFalse(self.context.active)
        self.assertEquals(self.context.header, None)

        self.assertIdentical(self.context, self.channel.consumer)

    def test_write(self):
        self.assertFalse(self.context.active)
        self.assertEquals(self.buffer.tell(), 0)
        self.assertEquals(self.encoder.activeChannels, set([]))

        self.context.write('hello')
        self.assertTrue(self.context.active)
        self.assertEquals(self.buffer.getvalue(), 'hello')
        self.assertEquals(self.buffer.tell(), 5)

        self.assertEquals(self.encoder.activeChannels, set([self.channel]))

    def test_getRelativeHeader(self):
        h = DummyHeader(relative=False, channelId=3, bodyLength=50,
            timestamp=10)
        self.channel.setHeader(h)

        self.assertIdentical(self.context.getRelativeHeader(), h)
        self.assertIdentical(self.context.header, None)

        self.context.header = DummyHeader(relative=False, channelId=3,
            bodyLength=10, timestamp=2)

        h = self.context.getRelativeHeader()

        self.assertTrue(interfaces.IHeader.providedBy(h))
        self.assertTrue(h.relative)


class EncoderClassTestCase(BaseEncoderTestCase):
    """
    Tests for L{codec.Encoder}
    """

    def test_job(self):
        self.assertEquals(self.encoder.getJob(), self.encoder.encode)
