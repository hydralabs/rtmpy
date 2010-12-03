# Copyright the RTMPy Project
#
# RTMPy is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# RTMPy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with RTMPy.  If not, see <http://www.gnu.org/licenses/>.

"""
Meta data and helper functions for setup
"""

import os.path
import sys

from setuptools.command import test
from setuptools import Extension

try:
    from Cython.Distutils import build_ext

    have_cython = True
except ImportError:
    from setuptools.command.build_ext import build_ext

    have_cython = False


keywords = """
rtmp flv rtmps rtmpe rtmpt rtmpte amf amf0 amf3 flex flash http https
streaming video audio sharedobject webcam record playback pyamf client
flashplayer air actionscript decoder encoder gateway server
""".strip()

_version = None


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


def get_version():
    global _version

    if _version:
        return _version

    try:
        f = open('version.txt', 'rt')
    except OSError:
        print ("ERROR: Unable to determine version (missing version.txt?)")

        raise SystemExit

    _version = f.read().strip()

    f.close()

    return _version


def is_pre_release():
    version_string = get_version()

    return "dev" in version_string or "alpha" in version_string or "beta" in version_string


def extra_setup_args():
    return {'cmdclass': {
       'test': TestCommand,
       'build_ext': build_ext,
    }}


def get_install_requirements():
    """
    Returns a list of dependencies for RTMPy to function correctly on the
    target platform.
    """
    install_requires = ['Twisted>=2.5.0', 'PyAMF>=0.6']

    if sys.platform.startswith('win'):
        install_requires.append('PyWin32')

    return install_requires



def get_test_requirements():
    """
    Returns a list of required packages to run the test suite.
    """
    tests_require = []

    if sys.version_info < (2, 7):
        tests_require.append('unittest2')

    return tests_require



def get_cpyamf_pxd_dir():
    """
    Return the directory that will be included to allow Cython to find
    cpyamf/*.pxd files (if cpyamf is installed)
    """
    try:
        import cpyamf
    except ImportError:
        print ("WARNING: cpyamf is not installed")

        return

    # TODO: what to do about pyamf in an egg here?
    return os.path.dirname(os.path.dirname(cpyamf.__file__))



def make_extension(mod_name, **extra_options):
    """
    Tries is best to return an Extension instance based on the mod_name
    """
    include_dirs = extra_options.setdefault('include_dirs', [])

    base_name = os.path.join(mod_name.replace('.', os.path.sep))

    if have_cython:
        cpd = get_cpyamf_pxd_dir()

        if cpd and cpd not in include_dirs:
            include_dirs.append(cpd)

        for ext in ['.pyx', '.py']:
            source = base_name + ext

            if os.path.exists(source):
                return Extension(mod_name, [source], **extra_options)

        print('WARNING: Could not find Cython source for %r' % (mod_name,))
    else:
        source = base_name + '.c'

        if os.path.exists(source):
            return Extension(mod_name, [source], **extra_options)

        print ('WARNING: Could not build extension for %r, no source found' % (
            mod_name))


def get_extensions():
    """
    Return a list of Extension instances that can be compiled.
    """
    extensions = []
    mods = [
        'rtmpy.protocol.rtmp.header'
    ]

    for m in mods:
        e = make_extension(m)

        if e:
            extensions.append(e)

    return extensions



def get_trove_classifiers():
    """
    Return a list of trove classifiers that are setup dependent.
    """
    classifiers = []

    def dev_status():
        version = get_version()

        if 'dev' in version:
            return 'Development Status :: 2 - Pre-Alpha'
        elif 'alpha' in version:
            return 'Development Status :: 3 - Alpha'
        elif 'beta' in version:
            return 'Development Status :: 4 - Beta'
        else:
            return 'Development Status :: 5 - Production/Stable'

    return [dev_status()]
