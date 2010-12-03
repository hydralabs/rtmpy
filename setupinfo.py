"""
Meta data and helper functions for setup
"""

import sys

from setuptools.command import test

try:
    from Cython.Distutils import build_ext
    have_cython = True
except ImportError:
    from setuptools.command.build_ext import build_ext


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



def get_extensions():
    src_ext = '.pyx'

    if not have_cython:
        src_ext = '.c'

    extensions = []

    base_name = 'rtmpy'
    root_dir = os.path.normpath(os.path.join(os.getcwd(), base_name))

    for root, _, files in os.walk(root_dir):
        for f in files:
            name, e = os.path.splitext(f)

            if e != src_ext:
                continue

            src = os.path.join(base_name, root[len(root_dir) + 1:], name)
            mod = src.replace(os.path.sep, '.')

            print src + src_ext, mod
            extensions.append(Extension(mod, [src + src_ext]))

    print extensions
    return extensions


def get_trove_classifiers():
    """
    Return a list of trove classifiers that are setup dependent.
    """
    classifiers = []

    def dev_status():
        version = get_version()

        if 'dev' in version:
            return 'Development Status :: 3 - Alpha'
        elif 'alpha' in version:
            return 'Development Status :: 3 - Alpha'
        elif 'beta' in version:
            return 'Development Status :: 4 - Beta'
        else:
            return 'Development Status :: 5 - Production/Stable'

    return [dev_status()]
