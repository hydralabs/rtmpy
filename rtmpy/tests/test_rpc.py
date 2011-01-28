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
Tests for L{rtmpy.rpc}.
"""


from twisted.trial import unittest

from rtmpy import rpc



class CallHandlerTestCase(unittest.TestCase):
    """
    Tests for L{rpc.BaseCallHandler}.
    """

    def setUp(self):
        self.handler = rpc.BaseCallHandler()


    def test_initiate(self):
        """
        Initiating a call should store the context that was passed to the call
        and return a unique, incrementing id.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        self.assertEqual(h.getNextCallId(), 1)
        self.assertEqual(h.getCallContext(1), None)

        self.assertEqual(h.initiateCall(*c), 1)
        self.assertEqual(h.getCallContext(1), c)

        self.assertEqual(h.getNextCallId(), 2)
        self.assertEqual(h.getCallContext(2), None)


    def test_active(self):
        """
        Ensure that L{rpc.BaseCallHandler.isCallActive} returns some sane
        results.
        """
        h = self.handler

        self.assertEqual(h.getNextCallId(), 1)

        self.assertFalse(h.isCallActive(1))

        callId = h.initiateCall()

        self.assertTrue(h.isCallActive(callId))


    def test_finish_non_active(self):
        """
        Finishing a call that is not active should result in no state change
        and C{None} should be returned.
        """
        h = self.handler
        hsh = hash(h)

        self.assertFalse(h.isCallActive(1))

        self.assertEqual(h.finishCall(1), None)
        self.assertEqual(hsh, hash(h))


    def test_finish_active_call(self):
        """
        Finishing an active call should return the original context supplied to
        C{initiateCall} and the call should no longer be active.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        callId = h.initiateCall(*c)

        self.assertEqual(h.finishCall(callId), c)
        self.assertFalse(h.isCallActive(callId))


    def test_discard_non_active(self):
        """
        Discarding a call that is not active should result in no state change
        and C{None} should be returned.
        """
        h = self.handler
        hsh = hash(h)

        self.assertFalse(h.isCallActive(1))

        self.assertEqual(h.discardCall(1), None)
        self.assertEqual(hsh, hash(h))


    def test_discard_active_call(self):
        """
        Discarding an active call should return the original context supplied to
        C{initiateCall} and the call should no longer be active.
        """
        h = self.handler
        c = ('foo', ['bar', 'baz'], {})

        callId = h.initiateCall(*c)

        self.assertEqual(h.discardCall(callId), c)
        self.assertFalse(h.isCallActive(callId))
