import pkg_resources
pkg_resources.require("twisted")

import sys
import traceback

from util import StringIO
from twisted.web import http
from twisted.internet.protocol import Protocol
from twisted.internet import reactor, protocol

import logging
from logging import debug, info, warning

import rtmp
import remoting

server_start_time = None

def main(mode, server='localhost'):

    logging.basicConfig(level=logging.DEBUG,
            format="%(asctime)s %(levelname)s %(message)s")

    rtmpPort = 1935
    httpPort = 8080
    
    if mode == "server":
        # start amf and rtmp servers
        reactor.listenTCP(httpPort, remoting.FlashRemotingFactory())
        reactor.listenTCP(rtmpPort, rtmp.RTMPServerFactory())
        print 'RTMPy Server started.'
        print 60 * '='
        reactor.run()
        print 'RTMPy Server stopped.'
        return 0
    elif mode == "client":
        f = rtmp.RTMPClientFactory()
        # start amf client
        reactor.connectTCP(server, rtmpPort, f)
        print 'RTMPy Client started.'
        print 60 * '='
        reactor.run()
        print 'RTMPy Client stopped.'
        return 0

if __name__ == '__main__':
    import sys
    sys.exit(main(*(sys.argv[1:])))
    
