import cython

from cpyamf.util cimport cBufferedByteStream
from cpython cimport exc


cdef class Header:
    cdef public int channelId
    cdef public int timestamp
    cdef public int datatype
    cdef public int bodyLength
    cdef public int streamId


@cython.locals(size=cython.int, channelId=cython.int)
cpdef object encode(cBufferedByteStream stream, Header header, Header previous=?)

@cython.locals(channelId=cython.int, bits=cython.int)
cpdef object decode(cBufferedByteStream stream)

@cython.locals(merged=Header)
cpdef Header merge(Header old, Header new)

cdef int min_bytes_required(Header old, Header new) except -1