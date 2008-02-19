# -*- test-case-name: rtmpy.tests.test_util -*-
#
# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

"""
RTMPy Utilities.

@author: U{Nick Joyce<mailto:nick@boxdesign.co.uk>}
@since: 0.1
"""

import sys

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from pyamf.util import BufferedByteStream

def uptime_win32():
    import win32api

    return win32api.GetTickCount()

def uptime_linux():
    try:
        fp = open('/proc/uptime')
    except IOError:
        return 0

    buffer = fp.read()
    fp.close()

    return int(float(buffer.split(" ")[0]) * 1000)

def uptime_mac():
    raise NotImplementedError

if sys.platform.startswith('linux'):
    uptime = uptime_linux
elif sys.platform.startswith('win'):
    uptime = uptime_win32
elif sys.platform.startswith('darwin'):
    uptime = uptime_mac()
else:
    uptime = lambda: 0
