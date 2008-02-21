# -*- test-case-name: rtmpy.tests.test_util -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
RTMPy Utilities.

@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}
@since: 0.1
"""

import os, sys, time

# the number of milliseconds since the epoch
boottime = None

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from pyamf.util import BufferedByteStream

def uptime_win32():
    """
    Returns the number of seconds since the epoch.

    @rtype: C{float}
    """ 
    import win32api

    return float(time.time()) - float(win32api.GetTickCount() / 1000)

def uptime_linux():
    """
    Returns the number of seconds since the epoch.

    @rtype: C{float}
    """ 
    try:
        fp = open('/proc/uptime')
    except IOError:
        return 0

    buffer = fp.read()
    fp.close()

    return float(time.time()) - float(buffer.split(" ")[0])

def uptime_darwin():
    """
    Returns the number of milliseconds since the kernel was started.
    """ 
    try:
        fp = os.popen('sysctl -nb kern.boottime')
    except IOError:
        return 0

    buffer = fp.read()
    fp.close()

    return float(time.time()) - float(buffer.strip())

def uptime():
    """
    Returns the number of milliseconds since the system was booted.

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

        up_func = lambda: time.time()

    boottime = int(up_func() * 1000)

    return now - boottime
