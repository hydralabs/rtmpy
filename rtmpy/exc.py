# Copyright the RTMPy Project.
# See LICENSE.txt for details.

"""
RTMPy exception types.
"""


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


class PublishError(BaseError):
    """
    Base error for all NetStream publishing errors.
    """


class BadNameError(PublishError):
    """
    Raised when a peer attempts to publish a stream with the same name as an
    already published stream.
    """

    code = 'NetStream.Publish.BadName'


class PlayError(BaseError):
    """
    Base error for all NetStream playing errors.
    """


class StreamNotFound(PlayError):
    """
    Raised when the corresponding stream could not be found for a play request.
    """

    code = 'NetStream.Play.StreamNotFound'
