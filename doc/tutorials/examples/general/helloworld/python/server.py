from rtmpy import server

from twisted.internet import reactor


class LiveApplication(server.Application):
    """
    Live app.
    """

    def clientDisconnected(self, client, reason):
        print 'client "%s" disconnected: %s' % (client, reason)


app = LiveApplication()

reactor.listenTCP(1935, server.ServerFactory({
    'live': app,
    'oflaDemo': app
}))

reactor.run()