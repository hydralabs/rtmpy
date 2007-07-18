class Notify:
    """ Stream notification event."""
    def __init__(self):
        self.name = None
        self.id = None
        self.argv = None
    
    def __repr__(self):
        return ("<Notify name=%r id=%r argv=%r>"
                % (self.name, self.id, self.argv))
