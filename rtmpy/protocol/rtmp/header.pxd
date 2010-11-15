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

import cython

from cpyamf.util cimport cBufferedByteStream
from cpython cimport exc


cdef class Header:
    cdef public int channelId
    cdef public int timestamp
    cdef public int datatype
    cdef public int bodyLength
    cdef public int streamId
    cdef public bint full
    cdef public bint continuation


@cython.locals(size=cython.int, channelId=cython.int)
cpdef object encode(cBufferedByteStream stream, Header header, Header previous=?)

@cython.locals(channelId=cython.int, bits=cython.int, header=Header)
cpdef Header decode(cBufferedByteStream stream)

@cython.locals(merged=Header)
cpdef Header merge(Header old, Header new)

cdef int min_bytes_required(Header old, Header new) except -1