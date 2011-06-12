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
Tests for L{rtmpy.core}
"""

from twisted.trial import unittest

from rtmpy import core, message, status



class SimpleStream(object):
    """
    @ivar closed: Set to C{True} when L{closeStream} is called.
    """

    closed = False

    def closeStream(self):
        self.closed = True



class SimpleStreamManager(core.StreamManager):
    """
    L{core.BaseStreamManager} requires that subclasses implement L{buildStream}
    """

    builtStreams = 0
    streamClass = SimpleStream


    def getControlStream(self):
        """
        Gets the control stream for the manager
        """
        return self


    def buildStream(self, streamId):
        """
        Build and return a L{SimpleStream} that has the streamId associated.
        """
        s = self.streamClass()

        s.streamId = streamId

        self.builtStreams += 1

        return s


    def closeStream(self):
        """
        We need this since we are the control stream.
        """



class TestRuntimeError(RuntimeError):
    """
    An exception class specifically used for testing error handling.
    """



class ErrorClosingStream(object):
    """
    Throws an error if L{closeStream} is called.
    """

    def closeStream(self):
        raise TestRuntimeError



class StreamManagerTestCase(unittest.TestCase):
    """
    Tests for L{core.BaseStreamManager}
    """


    def buildManager(self, cls=SimpleStreamManager):
        return cls()


    def test_get_stream_0(self):
        """
        streamID of 0 is special. It should return the manager.
        """
        m = self.buildManager()

        self.assertIdentical(m, m.getStream(0))


    def test_get_unknown(self):
        """
        Ensure that a call to L{getStream} for an non-existent stream will cause
        an error.
        """
        m = self.buildManager()

        self.assertEqual(m.builtStreams, 0)
        self.assertRaises(KeyError, m.getStream, 1)
        self.assertEqual(m.builtStreams, 0)


    def test_create(self):
        """
        Check basic stream creation
        """
        m = self.buildManager()

        streamId = m.createStream()

        self.assertEqual(m.builtStreams, 1)
        self.assertEqual(streamId, 1)


    def test_get_cache(self):
        """
        Getting the same stream id in succession should return the same stream
        instance.
        """
        m = self.buildManager()

        streamId = m.createStream()
        s = m.getStream(streamId)

        self.assertIdentical(s, m.getStream(streamId))


    def test_delete_stream_0(self):
        """
        Attempts to delete stream 0 should be ignored.
        """
        m = self.buildManager()

        m.deleteStream(0)
        self.assertIdentical(m, m.getStream(0))


    def test_delete_unknown(self):
        """
        Attempt to delete a stream that has not been created.
        """
        m = self.buildManager()

        self.assertRaises(KeyError, m.getStream, 1)
        m.deleteStream(1)


    def test_delete(self):
        """
        Deleting a stream should make that stream unavailable via the manager
        and call C{deleteStream} on the deleted stream.
        """
        m = self.buildManager()

        streamId = m.createStream()
        s = m.getStream(streamId)

        m.deleteStream(streamId)

        self.assertTrue(s.closed)
        self.assertRaises(KeyError, m.getStream, streamId)


    def test_deleted_id_reuse(self):
        """
        The manager should be aggressive its reuse of streamIds from recently
        deleted streams.
        """
        m = self.buildManager()

        [m.createStream() for i in xrange(50)]
        ids_to_delete = [23, 14, 46, 2]

        for streamId in ids_to_delete:
            m.deleteStream(streamId)

        created_stream_ids = [m.createStream() for i in xrange(len(ids_to_delete))]

        self.assertEqual(created_stream_ids, ids_to_delete)


    def test_close_all(self):
        """
        A close all operation should result with an empty manager, with all the
        streams having their C{closeStream} method called.
        """
        m = self.buildManager()
        n = 10

        # create a bunch of streams
        [m.createStream() for i in xrange(n)]
        self.assertEqual(m.builtStreams, n)

        streams = [m.getStream(i) for i in xrange(1, n + 1)]

        m.closeAllStreams()

        for stream in streams:
            self.assertTrue(stream.closed)
            self.assertRaises(KeyError, m.getStream, stream.streamId)

        self.assertEqual(m.getNextAvailableStreamId(), 1)


    def test_close_all_error(self):
        """
        Calling closeAllStreams should result in the correct state of the
        manager, even if an exception is raised whilst closing an individual
        stream.
        """
        m = self.buildManager()
        m.streamClass = ErrorClosingStream

        n = 10

        # create a bunch of streams
        [m.createStream() for i in xrange(n)]

        m.closeAllStreams()

        self.flushLoggedErrors(TestRuntimeError)

        self.assertEqual(m.streams, {0: m})
        self.assertEqual(m.getNextAvailableStreamId(), 1)



class StreamTimestampTestCase(unittest.TestCase):
    """
    Test stream timestamp operations.
    """


    def setUp(self):
        self.stream = core.BaseStream(None)


    def test_default(self):
        """
        Test simple construction and initial values.
        """
        self.assertEqual(self.stream.timestamp, 0)


    def test_absolute(self):
        """
        Set the timestamp in an absolute fashion.
        """
        s = self.stream
        self.assertEqual(s.timestamp, 0)

        s.setTimestamp(345678, False)
        self.assertEqual(s.timestamp, 345678)

        s.setTimestamp(2, False)
        self.assertEqual(s.timestamp, 2)


    def test_relative(self):
        """
        Set the timestamp in an relative fashion.
        """
        s = self.stream
        self.assertEqual(s.timestamp, 0)

        s.setTimestamp(123)
        self.assertEqual(s.timestamp, 123)

        s.setTimestamp(50, True)
        self.assertEqual(s.timestamp, 173)

        s.setTimestamp(-10, True)
        self.assertEqual(s.timestamp, 163)

        s.setTimestamp(5)
        self.assertEqual(s.timestamp, 168)



class MessageSendingStream(core.BaseStream):
    """
    A simple stream that stores the messages that that is sent through it
    """

    def __init__(self, streamId):
        core.BaseStream.__init__(self, streamId)

        self.messages = []


    def sendMessage(self, msg, whenDone=None):
        self.messages.append(msg)



class SendStatusTestCase(unittest.TestCase):
    """
    Tests for L{core.BaseStream.sendMessage}
    """

    def setUp(self):
        self.stream = MessageSendingStream(None)
        self.messages = self.stream.messages


    def checkMessage(self, msg, **kwargs):
        """
        Ensures that the supplied msg is formatted as a onStatus invoke.

        @param msg: The L{message.IMessage} to check.
        @param kwargs: Optional parameters to check. Valid keys are 'command',
            'level, 'code', 'description' and 'extra'.
        """
        sentinel = object()

        def check(a, b):
            c = kwargs.pop(b, sentinel)

            if c is sentinel:
                return

            self.assertEqual(a, c)

        self.assertTrue(message.typeByClass(msg), message.Invoke)

        self.assertEqual(msg.name, 'onStatus')
        self.assertEqual(msg.id, 0)

        cmd, s = msg.argv

        check(cmd, 'command')
        check(s.level, 'level')
        check(s.code, 'code')
        check(s.description, 'description')
        check(s.getExtraContext(), 'extra')

        # sanity check
        self.assertEqual(kwargs, {}, msg='improper use of checkMessage')


    def test_simple_string(self):
        """
        Supplying only code as a string to L{sendStatus} should yield a status
        message.
        """
        self.stream.sendStatus('foobar')

        msg = self.messages.pop()

        self.assertEqual(self.messages, [])

        self.checkMessage(msg, code='foobar')


    def test_status(self):
        """
        Sending a L{status.IStatus} should succeed.
        """
        s = status.error('AnErrorOccurred', 'This is a description', foo='bar')
        self.stream.sendStatus(s)

        msg = self.messages.pop()

        self.assertEqual(self.messages, [])

        self.checkMessage(msg, level='error', code='AnErrorOccurred',
            description='This is a description', extra={'foo': 'bar'})


    def test_command(self):
        """
        Sending a command arg with sendStatus should set the command var on the
        invoke message.
        """
        self.stream.sendStatus(None, command='blarg')

        msg = self.messages.pop()

        self.assertEqual(self.messages, [])

        self.checkMessage(msg, command='blarg')


    def test_extra(self):
        """
        Sending a code and description should allow extra key/value pairs to be
        set on the status object.
        """
        self.stream.sendStatus(None, None, spam='eggs', blarg='blaggity')

        msg = self.messages.pop()

        self.assertEqual(self.messages, [])

        self.checkMessage(msg, extra={'blarg': 'blaggity', 'spam': 'eggs'})



class NetConnectionTestCase(unittest.TestCase):
    """
    Tests for L{core.NetConnection}
    """

    def test_create(self):
        """
        Ensure we can actually create L{core.NetConnection} objects and check
        some defaults.
        """
        nc = core.NetConnection(None)

        self.assertEqual(nc.streamId, 0)
        self.assertEqual(nc.client, None)


    def test_control_stream(self):
        """
        Ensure that the control stream for L{core.NetConnection} is itself.
        """
        o = object()
        nc = core.NetConnection(o)

        self.assertIdentical(nc.getControlStream(), o)



class NetStreamTestCase(unittest.TestCase):
    """
    Tests for L{core.NetStream}
    """

    def setUp(self):
        self.nc = core.NetConnection(None)


    def test_create(self):
        """
        Ensure we can actually create L{core.NetStream} objects and check
        some defaults.
        """
        s = core.NetStream(self.nc, 2)

        self.assertEqual(s.streamId, 2)
        self.assertEqual(s.timestamp, 0)


    def test_client(self):
        """
        The client property on L{core.NetStream} should be identical to that of
        its C{NetConnection}.
        """
        client = object()
        self.nc.client = client

        s = core.NetStream(self.nc, None)

        self.assertIdentical(s.client, client)


    def test_close(self):
        """
        Ensure that we can close the stream.
        """
        s = core.NetStream(self.nc, None)

        s.closeStream()
