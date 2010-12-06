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

import unittest

from rtmpy import core



class SimpleStream(object):
    """
    """

    closed = False

    def closeStream(self):
        self.closed = True



class SimpleStreamManager(core.StreamManagerMixIn):
    """
    L{core.BaseStreamManager} requires that subclasses implement L{buildStream}
    """

    builtStreams = 0

    def buildStream(self, streamId):
        """
        Build and return a L{SimpleStream} that has the streamId associated.
        """
        s = SimpleStream()

        s.streamId = streamId

        self.builtStreams += 1

        return s



class StreamManagerTestCase(unittest.TestCase):
    """
    Tests for L{core.BaseStreamManager}
    """


    def buildManager(self, cls=SimpleStreamManager):
        return cls()


    def test_get_stream_0(self):
        """
        streamID of 0 is special. It should return the manager it self.
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

        ids = [m.createStream() for i in xrange(50)]
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
