# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Tests for L{rtmpy.versions}
"""

from twisted.trial import unittest

from rtmpy.versions import Version


class VersionTestCase(unittest.TestCase):
    """
    Tests for L{rtmpy.versions.Version}
    """

    def test_repr(self):
        v = Version('10,0,12,36')

        self.assertEquals(repr(v), 'rtmpy.versions.Version(10,0,12,36) ' \
            'at 0x%x' % (id(v),))

    def test_str(self):
        v = Version('10,0,12,36')

        self.assertEquals(str(v), '10,0,12,36')

    def test_init(self):
        e = self.assertRaises(ValueError, Version)
        self.assertEquals(str(e), 'Expected 4 parts for version (got:0)')

        # too many args
        e = self.assertRaises(ValueError, Version, 1, 2, 3, 4, 5)
        self.assertEquals(str(e), 'Expected 4 parts for version (got:5)')

        # single string
        v = Version('10,0,12,36')
        self.assertEquals(v.parts, [10, 0, 12, 36])

    def test_values(self):
        e = self.assertRaises(ValueError, Version, '10')
        self.assertEquals(str(e), 'Expected 4 parts for version (got:1)')

        e = self.assertRaises(ValueError, Version, '10,12,14,15,15')
        self.assertEquals(str(e), 'Expected 4 parts for version (got:5)')

        e = self.assertRaises(ValueError, Version, 'aa,bb,cc,dd,ee')
        self.assertEquals(str(e), 
            "invalid literal for int() with base 10: 'aa'")

        e = self.assertRaises(ValueError, Version, '10,13,14,-1')
        self.assertEquals(str(e), 'Invalid version number (received:-1)')

        e = self.assertRaises(ValueError, Version, '257,13,14,0')
        self.assertEquals(str(e), 'Invalid version number (received:257)')

        # as above but now with ints
        e = self.assertRaises(ValueError, Version, 10)
        self.assertEquals(str(e), 'Expected 4 parts for version (got:1)')

        e = self.assertRaises(ValueError, Version, 10, 12, 14, 15, 15)
        self.assertEquals(str(e), 'Expected 4 parts for version (got:5)')

        e = self.assertRaises(ValueError, Version, 10, 13, 14, -1)
        self.assertEquals(str(e), 'Invalid version number (received:-1)')

        e = self.assertRaises(ValueError, Version, 257, 13, 14, 0)
        self.assertEquals(str(e), 'Invalid version number (received:257)')

    def test_delete_int(self):
        v = Version('10,0,12,36')
        self.assertFalse(hasattr(v, '_int'))

        v._int = 'foo'
        v._buildParts('10', '0', '12', '36')
        self.assertFalse(hasattr(v, '_int'))

    def test_int(self):
        v = Version('10,0,12,36')

        self.assertFalse(hasattr(v, '_int'))
        self.assertEquals(int(v), 0x0a000c24)
        self.assertTrue(hasattr(v, '_int'))
        self.assertEquals(v._int, 0x0a000c24)

        v._int = 92
        self.assertEquals(int(v), 92)

    def test_cmp(self):
        va = Version(0, 1, 0, 0)
        vb = Version(0, 0, 1, 0)

        # Version instance comparisons
        self.failUnless(va > vb)
        self.failUnless(vb < va)
        self.failUnless(va >= vb)
        self.failUnless(vb <= va)
        self.failUnless(va != vb)
        self.failUnless(vb == Version(0, 0, 1, 0))
        self.failUnless(vb == vb)

        self.failIf(va < vb)
        self.failIf(vb > va)
        self.failIf(va <= vb)
        self.failIf(vb >= va)
        self.failIf(va == vb)
        self.failIf(vb != Version(0, 0, 1, 0))
        self.failIf(vb != vb)

        # int comparisons
        self.failUnless(va == 0x010000)
        self.failUnless(vb == 0x0100)

        self.failIf(va != 0x010000)
        self.failIf(va < 0x010000)
        self.failIf(va > 0x010000)
        self.failIf(vb != 0x0100)
        self.failIf(vb < 0x0100)
        self.failIf(vb > 0x0100)

        # string comparisons
        self.failUnless(va == '0,1,0,0')
        self.failUnless(vb == '0,0,1,0')

        self.failIf(va != '0,1,0,0')
        self.failIf(va < '0,1,0,0')
        self.failIf(va > '0,1,0,0')
        self.failIf(vb != '0,0,1,0')
        self.failIf(vb < '0,0,1,0')
        self.failIf(vb > '0,0,1,0')
