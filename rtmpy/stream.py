# -*- test-case-name: rtmpy.tests.test_stream -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
RTMP stream

@author: U{Arnar Birgisson<mailto:arnarbi@gmail.com>}
@author: U{Thijs Triemstra<mailto:info@collab.nl>}
@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}

@since: 0.1.0
"""

from twisted.internet import defer

from rtmpy import rtmp

STREAM_START_EVENT = intern("stream/start")
INIT_FAILED_EVENT = intern("rtmp/initfailed")

class Manager:
    """
    Base class for handling an RTMP connection.

    It is the responisibility of this class to dispatch the
    C{STREAM_START_EVENT}. This event tells the underlying RTMPStream that a
    valid connection has been established and is ready to begin exchanging
    RTMP Packets.
    """

    def __init__(self):
        self.stream = None

    def connectionMade(self):
        """
        Called by the RTMPStream when an underlying connection is made.
        """
        self.initialiseStream()

    def associateWithStream(self, stream):
        """
        Called by the RTMPStreamFactory when a connection has been made
        """
        self.stream = stream

    def initialiseStream(self):
        """
        Perform stream initialisation procedures.
        """
        def remove_first(result):
            self.stream.initialisers.pop(0)

            return result

        def do_next(result):
            """
            Take the first initializer and process it.

            On success, the initializer is removed from the list and then
            next initializer will be tried.
            """
            try:
                init = self.stream.initialisers[0]
            except IndexError:
                self.stream.dispatch(self.stream, STREAM_START_EVENT)

                return None
            else:
                d = defer.maybeDeferred(init.initialise)
                d.addCallback(remove_first)
                d.addCallback(do_next)

                return d

        d = defer.succeed(None)
        d.addCallback(do_next)
        d.addErrback(self.stream.dispatch, INIT_FAILED_EVENT)


class RTMPStream(rtmp.RTMPProtocol):
    """
    The base RTMP Protocol implementation for Twisted. Multiplexes attached
    channels into one TCP stream.

    @ivar channels: A list of objects connected to the stream.
    @type channels: C{dict}
    """
    initialisers = []
    manager = None

    def __init__(self, manager):
        self.manager = manager
