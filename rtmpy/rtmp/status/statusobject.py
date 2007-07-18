class StatusObject:
    """ Status object that is sent to client with every status event."""
    def __init__(self, code, level, description=None):
        self.code = code
        self.level = level
        self.description = description
    
    def __repr__(self):
        return ("<StatusObject code=%r level=%r description=%r>"
                % (self.code, self.level, self.description))
