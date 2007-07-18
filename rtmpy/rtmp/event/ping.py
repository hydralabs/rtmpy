class Ping:
    """ Ping event, actually combination of different events"""
    def __init__(self):
        self.value1 = None
        self.value2 = None
        self.value3 = None
        self.value4 = None
    
    def __repr__(self):
        return ("<Ping value1=%r value2=%r value3=%r value4=%r>"
                % (self.value1, self.value2, self.value3, self.value4))
