from twisted.web import http
from gateway import FlashRemotingGateway

class FlashRemoting(http.HTTPChannel):
    requestFactory = FlashRemotingGateway

class FlashRemotingFactory(http.HTTPFactory):
    protocol = FlashRemoting
