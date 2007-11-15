# -*- encoding: utf8 -*-
#
# Copyright (c) 2007 The RTMPy Project. All rights reserved.
# 
# Nick Joyce
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

"""
Echo client and server examples.

You can use this example with the echo_test.swf client on the
U{EchoTest<http://pyamf.org/wiki/EchoTest>} wiki page of the
U{PyAMF<http://pyamf.org>} website.

@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}
@author: U{Thijs Triemstra<mailto:info@collab.nl>}

@since: 0.1.0
"""

import os, os.path

def run_server(name, options, services):
    """
    Starts the echo RTMP server.

    @param options: commandline options
    @type options: dict
    @param services: List of services for the RTMP server.
    @type services: dict
    @return: The function that will run the server.
    @rtype: callable
    """
    from twisted.internet import reactor
    from rtmpy.rtmpprotocol import RTMPServerFactory

    print "Started %s - RTMP Server on rtmp://%s:%d" % (name, options.host, int(options.port))
    
    reactor.listenTCP(int(options.port), RTMPServerFactory(), 50, options.host)
    reactor.run()

def run_client(name, options, service, result_func, fault_func):
    """
    Starts the echo RTMP client.

    @param options: commandline options.
    @type options: dict
    @param service: Target service on the RTMP server.
    @type service: dict
    """
    
def parse_args(args):
    """
    Parse commandline options for echo test application.

    @param args:
    @type args:
    """
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-d', '--debug', action='store_true', dest='debug',
        default=False, help='Write RTMP request and response to disk')
    parser.add_option('--host', dest='host', default='localhost',
                      help='The host address for the RTMP server')
    parser.add_option('-p', '--port', dest='port', default=1935,
                      help='The port number for the RTMP server')

    return parser.parse_args(args)
