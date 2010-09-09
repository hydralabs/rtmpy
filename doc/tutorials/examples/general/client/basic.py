from twisted.internet import reactor
from rtmpy.client import ClientFactory

reactor.connectTCP('localhost', 1935, ClientFactory())
reactor.run()