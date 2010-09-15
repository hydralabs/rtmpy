"""
"""

class Status(object):
    """
    """

    class __amf__:
        static = ('level', 'code', 'description')

    def __init__(self, level, code, description, **kwargs):
        self.level = level
        self.code = code
        self.description = description

        self.__dict__.update(kwargs)

    def __repr__(self):
        return '<%s.%s %r at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self.__dict__,
            id(self)
        )

    def __eq__(self, other):
        return self.__dict__ == other


def status(code, description=None, **kwargs):
    """
    """
    return Status('status', code, description, **kwargs)


def error(code, description=None, **kwargs):
    """
    """
    return Status('error', code, description, **kwargs)
