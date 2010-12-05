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
RTMP status response objects require guaranteed attribute order otherwise the
Flash Player throws a fit.
"""


def status(code, description=None, **kwargs):
    """
    A helper method to return a status object with prefilled defaults.

    Use this if you want to return a success status for a given operation.
    """
    return Status('status', code, description, **kwargs)


def error(code, description=None, **kwargs):
    """
    Use this if you want to return a failure status for a given operation.
    """
    return Status('error', code, description, **kwargs)


class Status(object):
    """
    Represents a status response for a given RTMP call or operation.

    @ivar level: level of the status. Valid values appear to be 'status' or
        'error'.
    @ivar code: Represents the type of status/error being reported. See
        L{rtmpy.statuscodes} for a list.
    @ivar description: A description of the status.
    """

    class __amf__:
        static = ('level', 'code', 'description')

    def __init__(self, level, code, description, **kwargs):
        self.level = level
        self.code = code
        self.description = description

        self.__dict__.update(kwargs)

    def __repr__(self):
        return '<%s.%s %r at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self.__dict__,
            id(self)
        )

    def __eq__(self, other):
        return self.__dict__ == other

