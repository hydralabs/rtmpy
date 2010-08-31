# Copyright (c) The RTMPy Project.
# See LICENSE.txt for details.

from ez_setup import use_setuptools

use_setuptools()

import sys
from setuptools import setup, find_packages
from setuptools.command import test


class TestCommand(test.test):
    """
    Ensures that unittest2 is imported if required and replaces the old
    unittest module.
    """

    def run_tests(self):
        try:
            import unittest2
            import sys

            sys.modules['unittest'] = unittest2
        except ImportError:
            pass

        return test.test.run_tests(self)



def get_test_requirements():
    tests_require = []

    if sys.version_info < (2, 7):
        tests_require.append('unittest2')

    return tests_require


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
    install_requires = ['Twisted>=2.5.0', 'PyAMF>=0.6b2']

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
    cmdclass = {
       'test': TestCommand
    },
    url = "http://rtmpy.org",
    author = "The RTMPy Project",
    author_email = "rtmpy-dev@rtmpy.org",
    keywords = keyw,
    packages = find_packages(exclude=["*.tests"]),
    install_requires = get_install_requirements(),
    tests_require = get_test_requirements(),
    test_suite = "rtmpy.tests.get_suite",
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
