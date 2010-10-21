from rtmpy import server

from twisted.internet import reactor


class LiveApplication(server.Application):
    """
    The simplest application possible.
    """


app = LiveApplication()

reactor.listenTCP(1935, server.ServerFactory({
    'live': app,
    'oflaDemo': app # provides default support for the red5 publisher swf
}))

reactor.run()
