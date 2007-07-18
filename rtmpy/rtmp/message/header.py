class RTMPHeader:
    def __init__(self, channel):
        self.channel = channel
        self.timer = None
        self.size = None
        self.type = None
        self.streamId = None
    
    def __repr__(self):
        return ("<RTMPHeader channel=%r timer=%r size=%r type=%r (0x%02x) streamId=%r>"
                % (self.channel, self.timer, self.size, self.type, self.type or 0, self.streamId))
