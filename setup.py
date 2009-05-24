# Copyright (c) 2007-2009 The RTMPy Project.
# See LICENSE for details.

from ez_setup import use_setuptools

use_setuptools()

import sys
from setuptools import setup, find_packages

def get_version():
    """
    Gets the version number. Pulls it from the source files rather than
    duplicating it.
    """
    import os.path
    # we read the file instead of importing it as root sometimes does not
    # have the cwd as part of the PYTHONPATH

    fn = os.path.join(os.path.dirname(__file__), 'rtmpy', '__init__.py')
    lines = open(fn, 'rt').readlines()

    version = None

    for l in lines:
        # include the ' =' as __version__ is a part of __all__
        if l.startswith('__version__ =', ):
            x = compile(l, fn, 'single')
            eval(x)
            version = locals()['__version__']
            break

    if version is None:
        raise RuntimeError('Couldn\'t determine version number')

    return '.'.join([str(x) for x in version])

def get_install_requirements():
    """
    Returns a list of dependencies for RTMPy to function correctly on the
    target platform.
    """
    install_requires = ['Twisted>=2.5.0', 'PyAMF>=0.4.2']

    if sys.platform.startswith('win'):
        install_requires.append('PyWin32')

    return install_requires

keyw = """\
rtmp flv rtmps rtmpe rtmpt rtmpte amf amf0 amf3 flex flash http https
streaming video audio sharedobject webcam record playback pyamf client
flashplayer air actionscript decoder encoder gateway server"""

setup(name = "RTMPy",
    version = get_version(),
    description = "Twisted protocol for RTMP",
    long_description = open('README.txt', 'rt').read(),
    url = "http://rtmpy.org",
    author = "The RTMPy Project",
    author_email = "rtmpy-dev@rtmpy.org",
    keywords = keyw,
    packages = find_packages(exclude=["*.tests"]),
    install_requires = get_install_requirements(),
    zip_safe = True,
    license = "MIT License",
    platforms = ["any"],
    classifiers = [
        "Development Status :: 2 - Pre-Alpha",
        "Framework :: Twisted",
        "Natural Language :: English",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.3",
        "Programming Language :: Python :: 2.4",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ])
