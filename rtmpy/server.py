# -*- test-case-name: rtmpy.tests.test_server -*-
#
# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

"""
Server implementation.

@since: 0.1.0
"""

from zope.interface import Interface, Attribute, implements
from twisted.internet import reactor, protocol, defer
from twisted.python import log
from twisted.application import internet
import pyamf

from rtmpy import rtmp, util, dispatcher


class IApplication(Interface):
    """
    """

    clients = Attribute("A list of all clients connected to the application.")
    name = Attribute("The name of the application instance.")

    def startup():
        """
        Called when the server loads the application instance. Can return a
        deferred that signals that the application has fully initialized.
        """

    def shutdown():
        """
        Called when the application is unloaded. Can return a deferred that
        signals that the application has completely shutdown. Use this to
        close database connections etc.
        """

    def rejectConnection(client, reason):
        """
        Rejects the connection from the client, C{reason} being a
        L{failure.Failure} object or a string. Once the client has been
        rejected, the connection to the client must be closed.
        """

    def acceptConnection(client):
        """
        Called when the client has been accepted by this application.
        """

    def disconnect(client):
        """
        Disconnects a client from the application. Returns a deferred that is
        called when the disconnection was successful.
        """


class Application(object):
    """
    """

    implements(IApplication)

    def __init__(self):
        self.clients = []

    def startup(self):
        """
        Called when the application is starting up.
        """

    def shutdown(self):
        """
        Called when the application is closed.
        """

    def rejectConnection(self, client):
        """
        Called when a client connection request has been rejected.
        """
        # reject the connection and close
        # client.onStatus(...)
        client.close()

    def acceptConnection(self, client):
        """
        Called when this application has accepted the client connection. 
        """
        self.clients.append(client)

    def disconnect(self, client):
        """
        Removes the C{client} from this application.
        """
        self.clients.remove(client)


class ServerFactory(protocol.ServerFactory):
    """
    RTMP server protocol factory.
    """

    protocol = ServerProtocol

    def __init__(self, applications):
        self.applications = applications

        for app in self.applications.values():
            app.startup()

    def getApplication(self, name):
        """
        Returns the application mounted at C{name}, if any.
        """
        return self.applications.get(name, None)

    def buildProtocol(self, addr):
        p = protocol.ServerFactory.buildProtocol(self, addr)
        p.debug = True

        return p
