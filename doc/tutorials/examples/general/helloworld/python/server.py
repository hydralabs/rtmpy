from rtmpy import server

from twisted.internet import reactor


class LiveApplication(server.Application):
    """
    Live app.
    """

app = LiveApplication()

reactor.listenTCP(1935, server.ServerFactory({
    'live': app,
    'oflaDemo': app
}))

reactor.run()