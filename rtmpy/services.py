# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
RTMP services.

@author: U{Thijs Triemstra<mailto:info@collab.nl>}

@since: 0.1.0
"""

from twisted.application import internet
from twisted.internet import protocol

from rtmpy.rtmpprotocol import RTMPProtocol, Modes

class RTMPServerFactory(protocol.ServerFactory):
    """
    Construct RTMP servers.
    """
    #: protocol type
    protocol = RTMPProtocol
    #: handler type
    mode = Modes.SERVER

class RTMPClientFactory(protocol.ClientFactory):
    """
    Construct RTMP clients.
    """
    #: protocol type
    protocol = RTMPProtocol
    #: handler type
    mode = Modes.CLIENT

class RTMPServer(internet.TCPServer):
    """
    Twisted RTMP server.
    """
    def __init__(self, host, port):
        internet.TCPServer.__init__(self, port, RTMPServerFactory())

class RTMPClient(internet.TCPClient):
    """
    Twisted RTMP client.
    """
    def __init__(self, host, port):
        internet.TCPClient.__init__(self, host, port, RTMPClientFactory())
