# -*- encoding: utf8 -*-
#
# Copyright (c) 2007 The RTMPy Project. All rights reserved.
# 
# Thijs Triemstra
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

"""
RTMP services.
"""

from twisted.application import internet
from twisted.internet import protocol
from twisted.web import http

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

"""
class RemotingServer(internet.TCPServer):
    def __init__(self, host, port):
        internet.TCPServer.__init__(self, port, RemotingServerFactory())
        
class FlashRemoting(http.HTTPChannel):
    requestFactory = FlashRemotingGateway

class RemotingServerFactory(http.HTTPFactory):
    protocol = FlashRemoting
"""
