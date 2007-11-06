# -*- encoding: utf8 -*-
#
# Copyright (c) 2007 The RTMPy Project. All rights reserved.
# 
# Arnar Birgisson
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
Twisted RTMP/AMF server example.
"""

import sys

from twisted.application import service
from twisted.python import usage
import twisted.scripts.twistd as td

import rtmpy.services
from rtmpy.services import RTMPServer # RemotingServer, 

rtmpMode = "server"
rtmpHost = "0.0.0.0"
rtmpPort = 1935
httpHost = "0.0.0.0"
httpPort = 8000

if __name__ == '__main__':
    tdcmds = ["-no", "-y", __file__]
    tdoptions = td.ServerOptions()
    try:
        tdoptions.parseOptions(tdcmds)
    except usage.UsageError, errortext:
        print '%s' % (errortext)
        sys.exit(1)
        
    #: run app with twistd
    td.runApp(tdoptions)

else:
    # Normal twistd startup.
    application = service.Application("RTMPy")

    #: Create a MultiService, and hook up a the RTMP
    #: and HTTP TCPServers as children.
    flashServices = service.MultiService()

    #: HTTP/AMF server.
    # remotingServer = RemotingServer(httpHost, httpPort)
    # remotingServer.setServiceParent(flashServices)

    #: RTMP server.
    rtmpServer = RTMPServer(rtmpHost, rtmpPort)
    rtmpServer.setServiceParent(flashServices)

    #: Connect services to the application.
    flashServices.setServiceParent(application)
