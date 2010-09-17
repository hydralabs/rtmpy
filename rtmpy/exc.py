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
    Base error class for all connection related errors.
    """


class ConnectFailed(ConnectError):
    """
    Raised as a basic error for when connection fails and there is no other
    specific type of error.
    """

    code = 'NetConnection.Connect.Failed'


class ConnectRejected(ConnectError):
    """
    Raised when the peers connection attempt is rejected by the application.
    """

    code = 'NetConnection.Connect.Rejected'


class InvalidApplication(NetConnectionError):
    """
    Raised when the peer attempts to connect to an invalid or unknown
    application.
    """

    code = 'NetConnection.Connect.InvalidApp'


class PublishError(Exception):
    """
    Base error for all NetStream publishing errors.
    """


class BadNameError(PublishError):
    """
    Raised when a peer attempts to publish a stream with the same name as an
    already published stream.
    """

    code = 'NetStream.Publish.BadName'
