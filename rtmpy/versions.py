# -*- test-case-name: rtmpy.tests.test_versions -*-

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
Versions for products.

@see: L{Version}
@since: 0.1
"""


class Version(object):
    """
    Represents a version number, e.g. C{10,0,12,36}.
    """

    def __init__(self, *args):
        if len(args) == 1:
            if isinstance(args[0], (int, long)):
                self._fromInt(args[0])

                return
            elif isinstance(args[0], basestring):
                # maybe a regex here?
                self._buildParts(*args[0].split(','))

                return

        self._buildParts(*args)

    def _fromInt(self, i):
        self.parts = []

        if i > 0xffffffff or i < 0:
            raise ValueError('positive int up to 0xffffffff expected ' \
                '(i:%d)' % (i,))

        for x in xrange(0, 4):
            self.parts.append((i >> (24 - (x * 8))) & 0xff)

        self._int = i

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
        Returns a 4 byte integer representing the version.
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


#: Minimum version of the Adobe Flash Player that supports H.264 streaming
FLASH_MIN_H264 = Version('9,0,115,0')

#: Minimum version of Adobe Flash Media Server that supports H.264 streaming
FMS_MIN_H264 = Version('3,0,1,1')
