from twisted.internet import protocol
from rtmpprotocol import RTMPProtocol
import rtmpprotocol

class RTMPServerFactory(protocol.ServerFactory):
    protocol = RTMPProtocol
    mode = rtmpprotocol.Modes.SERVER

class RTMPClientFactory(protocol.ClientFactory):
    protocol = RTMPProtocol
    mode = rtmpprotocol.Modes.CLIENT
