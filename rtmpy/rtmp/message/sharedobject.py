
class SharedObjectTypeMapping:
    """Shared Object event types mapping"""
    def __init__(self):
        # Types map
        self.typeMap = ["SERVER_CONNECT"]
        
    def toType(self, rtmpType):
        """Convert byte value of RTMP marker to event type"""
        # Return corresponding Shared Object event type
        return self.typeMap[rtmpType]

    def toByte(self, type):
        """Convert SO event type to byte representation that RTMP uses"""
        # Return byte representation of given event type
        return 0x01
    
    def __repr__(self, type):
        """String representation of type"""
        return ("<SharedObjectTypeMapping type=%r>"
                % ("server connect"))
