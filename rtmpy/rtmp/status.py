import pyamf


class Status(object):
    """
    """

    def __init__(self, level=None, code=None, description=None):
        self.level = level
        self.code = code
        self.description = description

    @staticmethod
    def _get_attrs(obj):
        return obj.__dict__

pyamf.register_class(Status, attrs=['level', 'code', 'description'], attr_func=Status._get_attrs)


def status(**kwargs):
    s = Status(level='status')

    for k, v in kwargs.iteritems():
        setattr(s, k, v)

    return s


def error(**kwargs):
    s = Status(level='error')

    for k, v in kwargs.iteritems():
        setattr(s, k, v)

    return s
