# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE.txt for details.

"""
Tests for L{rtmpy.rtmp.codec.header}.
"""

from twisted.internet import reactor, defer
from twisted.trial import unittest

from rtmpy.rtmp.codec import header

class DecodeHeaderByteTestCase(unittest.TestCase):
    """
    Tests for L{header.decodeHeaderByte}
    """

    def test_types(self):
        self.assertRaises(TypeError, header.decodeHeaderByte, 'asdfasd')
