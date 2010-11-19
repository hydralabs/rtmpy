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
RTMPy is a U{Twisted<http://twistedmatrix.com>} protocol implementing
U{RTMP<http://en.wikipedia.org/wiki/Real_Time_Messaging_Protocol>}.

@see: U{http://rtmpy.org}

@since: July 2007
@status: Pre-Alpha
@version: 0.1.0
"""

from pyamf import versions as v

__all__ = ['__version__']


#: RTMPy version number.
__version__ = v.Version(0, 1, 1)
