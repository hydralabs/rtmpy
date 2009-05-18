import pyamf


class Status(object):
    """
    """

    def __init__(self, level=None, code=None, description=None):
        self.level = level
        self.code = code
        self.description = description


pyamf.register_class(Status, attrs=['level', 'code', 'description'])


def status(**kwargs):
    s = Status(level='status')

    for k, v in kwargs.iteritems():
        setattr(s, k, v)

    return s

def success(**kwargs):
    return status(code=u'NetConnection.Connect.Success',
        description=u'Connection succeeded.', **kwargs)
