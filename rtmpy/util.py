# -*- test-case-name: rtmpy.tests.test_util -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
RTMPy Utilities.

@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}
@since: 0.1
"""

import sys, time

# the number of milliseconds since the epoch
boottime = None

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from pyamf.util import BufferedByteStream as _BufferedByteStream

class BufferedByteStream(_BufferedByteStream):
    """
    Contains specific functionality not available in L{PyAMF}
    """

    def consume(self):
        """
        Chops off the data that has already been read from the stream.

        @note: Leaves the internal pointer at the end of the stream.
        """
        bytes = self.read()
        self.truncate()

        if len(bytes) > 0:
            self.write(bytes)
            self.seek(0, 2)


def uptime_win32():
    """
    Returns the number of seconds between the epoch and when the system was
    booted.

    @rtype: C{float}
    """ 
    import win32api

    return float(time.time()) - float(win32api.GetTickCount() / 1000)

def uptime_linux():
    """
    Returns the number of seconds between the epoch and when the system was
    booted.

    @rtype: C{float}
    """
    import re

    try:
        fp = open('%s%s' % (os.path.sep, os.path.join('proc', 'uptime')))
    except IOError:
        return 0

    buffer = fp.read()
    fp.close()

    match = re.compile('^([0-9]+\.[0-9]{2})').match(buffer, 0)

    if match is None:
        return 0

    if len(match.groups()) < 1:
        return 0

    return float(time.time()) - float(match.groups()[0])

def uptime_darwin():
    """
    Returns the number of seconds between the epoch and when the system was
    booted.

    @rtype: C{float}
    """
    from twisted.internet import protocol, defer
    from twisted.python import failure, procutils

    try:
        command = procutils.which('sysctl')[0]
    except IndexError:
        return 0

    buffer = ''

    class _BackRelay(protocol.ProcessProtocol):
        def __init__(self, deferred):
            self.deferred = deferred
            self.s = StringIO()

        def errReceived(self, text):
            self.deferred.errback(failure.Failure(IOError()))
            self.deferred = None
            self.transport.loseConnection()

        def outReceived(self, text):
            self.s.write(text)

        def processEnded(self, reason):
            if self.deferred is not None:
                result = self.s.getvalue()
                self.deferred.callback(result)


    def getProcessOutput(executable, args=(), env={}, path='.'):
        from twisted.internet import reactor

        d = defer.Deferred()
        p = _BackRelay(d)

        reactor.spawnProcess(p, executable, args, env, path)

        return d

    def get_uptime():
        d = getProcessOutput(command, ('-nb', 'kern.boottime'))
        d.addErrback(lambda f: '')

        result = defer.waitForDeferred(d)
        yield result

        buffer = result.getResult()

    get_uptime = defer.deferredGenerator(get_uptime)

    get_uptime()

    import re

    match = re.compile('^([0-9]+)').match(buffer, 0)

    if match is None:
        return 0

    return float(time.time()) - float(buffer.strip())

def uptime():
    """
    Returns the number of milliseconds since the system was booted. This is
    system dependant, currently supported are Windows, Linux and Darwin.

    If a value cannot be calculated, a default value of when this function was
    first called is returned.

    @rtype: C{int}
    """
    global boottime

    now = int(time.time() * 1000)

    if boottime is not None:
        return now - boottime

    if sys.platform.startswith('linux'):
        up_func = uptime_linux
    elif sys.platform.startswith('win'):
        up_func = uptime_win32
    elif sys.platform.startswith('darwin'):
        up_func = uptime_darwin
    else:
        import warnings

        warnings.warn("Could not find a platform specific uptime " \
            "function for '%s'" % sys.platform, RuntimeWarning)

        up_func = lambda: 0

    boottime = int(up_func() * 1000)

    if boottime == 0:
        boottime = now

    return now - boottime
