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
RTMPy exception types.
"""

import sys

from rtmpy.status import codes


__all__ = ['codeByClass', 'classByCode']


#: A collection of known exception classes and their related status codes
CLASS_CODES = {}


def add_to_class(f, depth=1):
    def wrap(*args, **kwargs):
        # ripped from zope.interface
        frame = sys._getframe(depth)
        locals = frame.f_locals

        # Try to make sure we were called from a class def.
        if locals is frame.f_globals or '__module__' not in locals:
            raise TypeError(code + " can be used only from a class definition.")

        f(locals, *args)

    wrap.func_name = f.func_name
    wrap.__doc__ = f.__doc__

    return wrap


@add_to_class
def register(locals, code):
    locals['__status_code__'] = code



class BaseError(Exception):
    """
    Base exception class from which all others must be subclassed.
    """



class NetConnectionError(BaseError):
    """
    Base error class for all NetConnection errors.
    """



class CallFailed(NetConnectionError):
    """
    Raised when invoked methods from the peer fails for some reason.
    """

    register(codes.NC_CALL_FAILED)



class ConnectError(NetConnectionError):
    """
    Base error class for all connection related errors.
    """



class ConnectFailed(ConnectError):
    """
    Raised as a basic error for when connection fails and there is no other
    specific type of error.
    """

    register(codes.NC_CONNECT_FAILED)



class ConnectRejected(ConnectError):
    """
    Raised when the peers connection attempt is rejected by the application.
    """

    register(codes.NC_CONNECT_REJECTED)



class InvalidApplication(NetConnectionError):
    """
    Raised when the peer attempts to connect to an invalid or unknown
    application.
    """

    register(codes.NC_CONNECT_INVALID_APPLICATION)



class StreamError(BaseError):
    """
    Base NetStream errors.
    """

    register(codes.NS_FAILED)



class PublishError(StreamError):
    """
    Base error for all NetStream publishing errors.
    """



class BadNameError(PublishError):
    """
    Raised when a peer attempts to publish a stream with the same name as an
    already published stream.
    """

    register(codes.NS_PUBLISH_BADNAME)



class PlayError(BaseError):
    """
    Base error for all NetStream playing errors.
    """



class StreamNotFound(PlayError):
    """
    Raised when the corresponding stream could not be found for a play request.
    """

    register(codes.NS_PLAY_STREAMNOTFOUND)



def codeByClass(cls):
    """
    """
    global CLASS_CODES

    return CLASS_CODES.get(cls, None)



classByCode = codeByClass



for k, v in globals().items():
    try:
        if not issubclass(v, BaseError):
            continue
    except TypeError:
        continue

    __all__.append(k)

    if not hasattr(v, '__status_code__'):
        continue

    code = v.__status_code__

    CLASS_CODES[code] = v
    CLASS_CODES[v] = code

del k, v
