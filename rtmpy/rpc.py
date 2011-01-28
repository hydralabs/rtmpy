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
API for handling RTMP RPC calls.
"""



class BaseCallHandler(object):
    """
    Provides the ability to initiate, track and finish RPC calls. Each RPC call
    is given a unique id.

    Once a call is I{finished}, it is forgotten about. Call ids cannot be
    reused.

    @ivar _lastCallId: The value of the last initiated RPC call.
    @type _lastCallId: C{int}
    @ivar _activeCalls: A C{dict} of callId -> context. An active call has been
        I{initiated} but not yet I{finished}.
    """


    def __init__(self):
        self._lastCallId = 0
        self._activeCalls = {}


    def isCallActive(self, callId):
        """
        Whether the C{callId} is a valid identifier for a call awaiting a
        result.
        """
        return callId in self._activeCalls


    def getNextCallId(self):
        """
        Returns the next call id that will be returned by L{initiateCall}.

        This method is useful for unit testing.
        """
        return self._lastCallId + 1


    def getCallContext(self, callId):
        """
        Returns the context stored when L{initiateCall} was executed.

        If no active call is found, C{None} will be returned in its place.

        @param callId: The call id returned by the corresponding call to
            L{initiateCall}.
        @rtype: C{tuple} or C{None} if the call is not active.
        @note: Useful for unit testing.
        """
        return self._activeCalls.get(callId, None)


    def initiateCall(self, *args):
        """
        Starts an RPC call and stores any context for the call for later
        retrieval. The call will remain I{active} until L{finishCall} is called
        with the same C{callId}.

        @param args: The context to be stored whilst the call is active.
        @return: A id that uniquely identifies this call.
        @rtype: C{int}
        """
        callId = self._lastCallId = self.getNextCallId()

        self._activeCalls[callId] = args

        return callId


    def finishCall(self, callId):
        """
        Called to finish an active RPC call. The RPC call completed successfully
        (with some sort of response).

        @param callId: The call id returned by the corresponding call to
            L{initiateCall} that uniquely identifies the call.
        @return: The context with which this call was initiated or C{None} if no
            active call could be found.
        """
        return self._activeCalls.pop(callId, None)


    def discardCall(self, callId):
        """
        Called to discard an active RPC call. The RPC call was not completed
        successfully.

        The semantics of this method is different to L{finishCall}, it is useful
        for clearing up any active calls that failed for some arbitrary reason.

        @param callId: The call id returned by the corresponding call to
            L{initiateCall} that uniquely identifies the call.
        @return: The context with which this call was initiated or C{None} if no
            active call could be found.
        """
        return self._activeCalls.pop(callId, None)
