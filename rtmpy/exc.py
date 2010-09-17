# Copyright the RTMPy Project.
# See LICENSE.txt for details.

"""
RTMPy exception types.
"""


class NetConnectionError(Exception):
    """
    Base error class for all NetConnection errors.
    """


class CallFailed(NetConnectionError):
    """
    Raised when invoked methods from the peer fails for some reason.
    """

    code = 'NetConnection.Call.Failed'


class ConnectError(NetConnectionError):
    """
    """


class ConnectFailed(ConnectError):
    """
    """

    code = 'NetConnection.Connect.Failed'


class ConnectRejected(ConnectError):
    """
    """

    code = 'NetConnection.Connect.Rejected'


class InvalidApplication(NetConnectionError):
    """
    """

    code = 'NetConnection.Connect.InvalidApp'
