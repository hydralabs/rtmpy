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

from zope.interface import Interface, Attribute, implements


__all__ = ['IStatus', 'status', 'error', 'fromFailure']


STATUS_STATUS = 'status'
STATUS_ERROR = 'error'


class IStatus(Interface):
    """
    A status object is a generic notification about an operation or state of the
    endpoint, including error handling.

    Status objects are encoded in AMF and dispatched into (or received from) the
    RTMP message stream.

    All attributes specified in this interface are the minimum required values
    for a valid status object.

    All attributes are of type C{unicode} unless explicitly specified.
    """


    level = Attribute('The level of the notification. Valid values appear to be'
        ' C{status} and C{error}.')
    code = Attribute('A label used to distinguish between different types of '
        'notification. The structure of this string appears to be B{.} '
        'separated depending on the context of the notification. See '
        'L{rtmpy.core.status.codes} for a list of known values.')
    description = Attribute('A humanised description of the notification.')



def status(code, description, **kwargs):
    """
    Returns a L{IStatus} object.

    Use this if you want to return a success notification for a given operation.

    @param code: The code of the status. See L{rtmpy.core.status.codes} for a
        list of valid values.
    @param description: A humanised description of the successful operation.
    @param kwargs: A C{dict} of values that will be added to the status object
        and will be dispatched to the receiving endpoint.
    """
    # prevent circular import
    from rtmpy import exc

    code = exc.codeByClass(code) or code

    return Status(STATUS_STATUS, code, description, **kwargs)



def error(code, description, **kwargs):
    """
    Returns a L{IStatus} in an error state.

    Use this if you want to return a failure notification for a given operation.

    @param code: The code of the status. See L{rtmpy.status.codes} for a
        list of valid values.
    @param description: A humanised description of the successful operation.
    @param kwargs: A C{dict} of values that will be added to the status object
        and will be dispatched to the receiving endpoint.
    """
    # prevent circular import
    from rtmpy import exc

    code = exc.codeByClass(code) or code

    return Status(STATUS_ERROR, code, description, **kwargs)



def fromFailure(fail, defaultCode=None):
    """
    Returns an error status notification based on the supplied
    L{twisted.python.failure.Failure} object.

    @return: L{IStatus} in an error state based upon the supplied failure object.
    """
    # prevent circular import
    from rtmpy import exc

    cls = type(fail.value)

    code = exc.codeByClass(cls) or exc.codeByClass(defaultCode) or defaultCode
    description = fail.getErrorMessage()

    return error(code, description)



class Status(object):
    """
    A generic notification object for a given RTMP call or operation.

    @see: L{IStatus} for a more in-depth description.
    """


    implements(IStatus)


    class __amf__:
        # RTMP is very picky about the order of the required attributes.
        # any others, it doesn't seem to care about
        static = ('level', 'code', 'description')


    def __init__(self, level, code, description, **kwargs):
        self.level = level
        self.code = code
        self.description = description

        self.__dict__.update(kwargs)


    def __repr__(self):
        return '<%s: %s %r at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self.__dict__,
            id(self)
        )


    def __unicode__(self):
        return '%s: %s' % (self.code, self.description)


    def __eq__(self, other):
        return self.__dict__ == other


    def getExtraContext(self):
        """
        Returns a dict of any extra context that was supplied with the status.

        `extra` means any attributes on this instance excluding the L{IStatus}
        attributes.
        """
        d = self.__dict__.copy()

        d.pop('level', None)
        d.pop('code', None)
        d.pop('description', None)

        return d
