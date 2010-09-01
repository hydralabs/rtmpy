# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

import pyamf


class Status(object):
    """
    """

    class __amf__:
        static = ('level', 'code', 'description')

    def __init__(self, level=None, code=None, description=None):
        self.level = level
        self.code = code
        self.description = description

    def __repr__(self):
        return '<%s.%s %r at 0x%x>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self.__dict__,
            id(self)
        )


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
