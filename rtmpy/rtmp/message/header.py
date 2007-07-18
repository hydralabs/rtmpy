class RTMPHeader:
    def __init__(self, channel, timer=0, size=None, type=None, streamId=0):
        self.channel = channel
        self.timer = timer
        self.size = size
        self.type = type
        self.streamId = streamId
    
    def __repr__(self):
        return ("<RTMPHeader channel=%r timer=%r size=%r type=%r (0x%02x) streamId=%r>"
                % (self.channel, self.timer, self.size, self.type, self.type or 0, self.streamId))
