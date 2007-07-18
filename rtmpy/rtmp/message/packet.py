class RTMPPacket:
    """ RTMP packet. Consists of packet header, data and event context."""
    def __init__(self, header, data, message=None):
        self.header = header
        self.data = data
        self.message = message
    
    def __repr__(self):
        return ("<RTMPPacket message=%r header=%r>"
                % (self.message, self.header))
