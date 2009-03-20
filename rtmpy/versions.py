# -*- test-case-name: rtmpy.tests.test_versions -*-

# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Versions for Adobe products.

@see L{Version}
"""


class Version(object):
    """
    Represents a Flash version number, e.g. 10,0,12,36
    """

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], basestring):
            # maybe a regex here?
            self._buildParts(*args[0].split(','))

            return

        self._buildParts(*args)

    def _buildParts(self, *args):
        self.parts = []

        for a in args:
            a = int(a)

            if a < 0 or a > 256:
                raise ValueError('Invalid version number (received:%r)' % a)

            self.parts.append(a)

        if len(self.parts) != 4:
            raise ValueError('Expected 4 parts for version (got:%d)' % (
                len(self.parts),))

        if hasattr(self, '_int'):
            delattr(self, '_int')

    def __int__(self):
        """
        Returns a 4 byte integer representing the version
        """
        if hasattr(self, '_int'):
            return self._int

        self._int = 0

        for x in xrange(0, 4):
            self._int += self.parts[x] << (24 - (x * 8))

        return self._int

    def __str__(self):
        return ','.join([str(x) for x in self.parts])

    def __repr__(self):
        return '%s.%s(%s) at 0x%x' % (
            self.__class__.__module__,
            self.__class__.__name__,
            str(self),
            id(self))

    def __cmp__(self, other):
        if isinstance(other, (int, long)):
            return cmp(int(self), other)

        if isinstance(other, Version):
            return cmp(self.parts, other.parts)

        if isinstance(other, basestring):
            return cmp(str(self), other)
