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
Core primitives and logic for all things RTMP.
"""


#: A dictionary of
_exposed_funcs = {}


def expose(func):
    """
    A decorator that provides an easy way to expose methods that the peer can
    'call' via RTMP C{invoke} or C{notify} messages.

    Example usage::

        @expose
        def someRemoteMethod(self, foo, bar):
            pass

        @expose('foo-bar')
        def anotherExposedMethod(self, *args):
            pass

    If expose is called with no args, the function name is used.
    """
    if hasattr(func, '__call__'):
        _exposed_funcs[func.func_name] = func.func_name

        return func

    def decorator(f):
        _exposed_funcs[func] = f.func_name

        return f

    return decorator
