# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.rtmp.scheduler}.
"""

from twisted.internet import defer, task
from twisted.trial import unittest

from rtmpy.rtmp import interfaces, scheduler
from rtmpy.tests.rtmp import mocks


class BaseChannelSchedulerTestCase(unittest.TestCase):
    """
    Tests for L{codec.BaseChannelScheduler}.
    """

    def setUp(self):
        self._channelId = 0
        self.manager = mocks.ChannelManager()

    def _generateChannel(self):
        """
        """
        h = mocks.Header(channelId=self._channelId, relative=False)
        self._channelId += 1

        c = mocks.Channel()
        c.setHeader(h)
        c.registerManager(self.manager)
        c.reset()

        return c

    def _generateScheduler(self):
        return scheduler.BaseChannelScheduler()

    def test_create(self):
        s = self._generateScheduler()

        self.assertTrue(interfaces.IChannelScheduler.providedBy(s))
        self.assertEquals(s.activeChannels, [])

    def test_activateChannel(self):
        s = self._generateScheduler()
        c = self._generateChannel()

        self.assertEquals(s.activeChannels, [])

        s.activateChannel(c)
        self.assertTrue(c in s.activeChannels)

        e = self.assertRaises(IndexError, s.activateChannel, c)
        self.assertEquals(str(e), 'channel already activated')

    def test_deactivateChannel(self):
        s = self._generateScheduler()
        c = self._generateChannel()

        e = self.assertRaises(IndexError, s.deactivateChannel, c)
        self.assertEquals(str(e), 'channel not activated')

        s.activateChannel(c)
        s.deactivateChannel(c)
        self.assertFalse(c in s.activeChannels)
        self.assertEquals(s.activeChannels[0], None)

    def test_getNextChannel(self):
        s = self._generateScheduler()
        e = self.assertRaises(NotImplementedError, s.getNextChannel)


class LoopingChannelSchedulerTestCase(BaseChannelSchedulerTestCase):
    """
    Tests for L{codec.LoopingChannelScheduler}.
    """

    def _generateScheduler(self):
        return scheduler.LoopingChannelScheduler()

    def test_create(self):
        BaseChannelSchedulerTestCase.test_create(self)

        s = self._generateScheduler()

        self.assertEquals(s.index, None)

    def test_getNextChannel(self):
        # test no channels
        s = self._generateScheduler()

        self.assertEquals(s.activeChannels, [])
        self.assertEquals(s.getNextChannel(), None)
        self.assertEquals(s.index, None)

    def test_infiniteLoop_singleChannel(self):
        s = self._generateScheduler()
        c = self._generateChannel()

        s.activateChannel(c)

        self.assertIdentical(s.getNextChannel(), c)
        self.assertEquals(s.index, 0)
        self.assertIdentical(s.getNextChannel(), c)
        self.assertEquals(s.index, 0)

        s.deactivateChannel(c)
        self.assertEquals(s.getNextChannel(), None)

    def test_infiniteLoop_multipleChannel(self):
        s = self._generateScheduler()
        c1 = self._generateChannel()
        c2 = self._generateChannel()

        s.activateChannel(c1)
        s.activateChannel(c2)

        self.assertIdentical(s.getNextChannel(), c1)
        self.assertEquals(s.index, 0)
        self.assertIdentical(s.getNextChannel(), c2)
        self.assertEquals(s.index, 1)
        self.assertIdentical(s.getNextChannel(), c1)
        self.assertEquals(s.index, 0)
        self.assertIdentical(s.getNextChannel(), c2)
        self.assertEquals(s.index, 1)

        s.deactivateChannel(c1)
        self.assertEquals(s.getNextChannel(), c2)
        self.assertEquals(s.index, 1)
        self.assertEquals(s.getNextChannel(), c2)
        self.assertEquals(s.index, 1)

        s.deactivateChannel(c2)

        self.assertEquals(s.getNextChannel(), None)

    def test_allDeactivatedChannels(self):
        s = self._generateScheduler()
        c1 = self._generateChannel()
        c2 = self._generateChannel()

        s.activateChannel(c1)
        s.activateChannel(c2)

        s.deactivateChannel(c1)
        s.deactivateChannel(c2)

        self.assertEquals(len(s.activeChannels), 2)
        self.assertEquals(s.getNextChannel(), None)
        self.assertEquals(len(s.activeChannels), 0)
