# Copyright (c) 2007-2008 The RTMPy Project.
# See LICENSE for details.

from ez_setup import use_setuptools

use_setuptools()

import sys
from setuptools import setup, find_packages

install_requires = ['Twisted>=2.5.0', 'PyAMF>=0.1.1']

if sys.platform.startswith('win'):
    install_requires.append('PyWin32')

setup(name = "RTMPy",
    version = "0.1",
    description = "Twisted protocol for RTMP",
    url = "http://rtmpy.org",
    packages = ["rtmpy"],
    test_suite = "rtmpy.tests.suite",
    install_requires = install_requires,
    license = "MIT License",
    classifiers = [
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ])
