# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.codec}.
"""

from twisted.internet import defer, task
from twisted.trial import unittest

from rtmpy.rtmp import codec, interfaces
from rtmpy import util
from rtmpy.tests.rtmp import mocks

class BaseCodecTestCase(unittest.TestCase):
    """
    Tests for L{codec.BaseCodec}
    """

    @classmethod
    def _getJob(cls):
        return lambda: None

    def setUp(self):
        self._getJob = codec.BaseCodec.getJob
        codec.BaseCodec.getJob = BaseCodecTestCase._getJob

    def tearDown(self):
        codec.BaseCodec.getJob = self._getJob

    def test_job(self):
        d = mocks.ChannelManager()
        c = codec.BaseCodec(d)

        self.assertRaises(NotImplementedError, self._getJob, c)

    def test_init(self):
        e = self.assertRaises(TypeError, codec.BaseCodec, 'hello')
        self.assertEquals(str(e), "IChannelManager expected (got <type 'str'>)")

        obj = object()

        codec.BaseCodec.getJob = lambda self: obj

        d = mocks.ChannelManager()
        self.assertTrue(interfaces.IChannelManager.providedBy(d))
        c = codec.BaseCodec(d)

        self.assertIdentical(c.manager, d)
        self.assertEquals(c.deferred, None)
        self.assertTrue(isinstance(c.buffer, util.BufferedByteStream))
        self.assertTrue(isinstance(c.job, task.LoopingCall))

    def test_destroy_not_running(self):
        d = mocks.ChannelManager()
        c = codec.BaseCodec(d)

        self.assertFalse(c.job.running)

        c.__del__()

    def test_destroy_running(self):
        self.executed = False
        d = mocks.ChannelManager()
        c = codec.BaseCodec(d)

        def cb(lc):
            self.assertIdentical(c.job, lc)
            self.executed = True

        c.start().addCallback(cb)

        self.assertFalse(self.executed)
        c.__del__()
        self.assertTrue(self.executed)

    def test_start(self):
        d = mocks.ChannelManager()
        c = codec.BaseCodec(d)

        job = c.job

        self.assertEquals(c.deferred, None)
        self.assertFalse(job.running)

        x = c.start()

        self.assertTrue(x, defer.Deferred)
        self.assertIdentical(c.deferred, x)
        self.assertEquals(job.interval, 0)
        self.assertTrue(job.running)

        y = c.start()
        self.assertIdentical(c.deferred, x, y)

    def test_pause(self):
        d = mocks.ChannelManager()
        c = codec.BaseCodec(d)
        job = c.job
        c.deferred = object()

        self.assertFalse(job.running)
        c.pause()
        self.assertFalse(job.running)
        self.assertNotEquals(c.deferred, None)

        c.start()
        self.assertTrue(job.running)

        c.pause()
        self.assertFalse(job.running)
        self.assertEquals(c.deferred, None)
