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

import sys
import os.path
import fnmatch

try:
    from Cython.Distutils import build_ext

    have_cython = True
except ImportError:
    from setuptools.command.build_ext import build_ext

    have_cython = False


if have_cython:
    # may need to work around setuptools bug by providing a fake Pyrex
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fake_pyrex"))


from setuptools.command import test, sdist
from setuptools import Extension
from distutils.core import Distribution


_version = None

jython = sys.platform.startswith('java')
can_compile_extensions = not jython


class MyDistribution(Distribution):
    """
    This seems to be is the only obvious way to add a global option to
    distutils.

    Provide the ability to disable building the extensions for any called
    command.
    """

    global_options = Distribution.global_options + [
        ('disable-ext', None, 'Disable building extensions.')
    ]

    def finalize_options(self):
        Distribution.finalize_options(self)

        try:
            i = self.script_args.index('--disable-ext')
        except ValueError:
            self.disable_ext = False
        else:
            self.disable_ext = True
            self.script_args.pop(i)


class MyBuildExt(build_ext):
    """
    The companion to L{MyDistribution} that checks to see if building the
    extensions are disabled.
    """

    def build_extension(self, ext):
        if self.distribution.disable_ext:
            return

        return build_ext.build_extension(self, ext)

    def build_extensions(self):
        if self.distribution.disable_ext:
            return

        return build_ext.build_extensions(self)


class MySDist(sdist.sdist):
    """
    We generate the Cython code for a source distribution
    """

    def cythonise(self):
        ext = MyBuildExt(self.distribution)
        ext.initialize_options()
        ext.finalize_options()

        ext.check_extensions_list(ext.extensions)

        for e in ext.extensions:
            e.sources = ext.cython_sources(e.sources, e)


    def run(self):
        if not have_cython:
            print('ERROR - Cython is required to build source distributions')

            raise SystemExit(1)

        self.cythonise()

        return sdist.sdist.run(self)


class TrialTest(test.test):
    """
    Twisted Trial setuptools command

    Stolen from setuptools_trial.
    """

    user_options = test.test.user_options + [
        ('rterrors', 'e', "Realtime errors: print out tracebacks as soon as they occur."),
        ('debug-stacktraces', 'B', "Report Deferred creation and callback stack traces."),
        ('coverage','c', "Report coverage data."),
        ('reactor=','r', "which reactor to use"),
        ('reporter=', None, "Customize Trial's output with a Reporter plugin."),
        ('until-failure','u', "Repeat test until it fails."),
    ]

    boolean_options = ['coverage', 'debug-stacktraces', 'rterrors']

    def initialize_options(self):
        test.test.initialize_options(self)
        self.coverage = None
        self.debug_stacktraces = None
        self.reactor = None
        self.reporter = None
        self.rterrors = None
        self.until_failure = None

    def finalize_options(self):
        if self.test_suite is None:
            if self.test_module is None:
                self.test_suite = self.distribution.test_suite
            else:
                self.test_suite = self.test_module
        elif self.test_module:
            raise DistutilsOptionError(
                "You may specify a module or a suite, but not both"
            )

        self.test_args = self.test_suite

    def run_tests(self):
        # We do the import from Twisted inside the function instead of the top
        # of the file because since Twisted is a setup_requires, we can't
        # assume that Twisted will be installed on the user's system prior
        # to using Tahoe, so if we don't do the import here, then importing
        # from this plugin will fail.
        from twisted.scripts import trial

        # Handle parsing the trial options passed through the setuptools
        # trial command.
        cmd_options = []
        if self.reactor is not None:
            cmd_options.extend(['--reactor', self.reactor])
        else:
            # Cygwin requires the poll reactor to work at all.  Linux requires the poll reactor
            # to avoid twisted bug #3218.  In general, the poll reactor is better than the
            # select reactor, but it is not available on all platforms.  According to exarkun on
            # IRC, it is available but buggy on some versions of Mac OS X, so just because you
            # can install it doesn't mean we want to use it on every platform.
            # Unfortunately this leads to this error with some combinations of tools:
            # twisted.python.usage.UsageError: The specified reactor cannot be used, failed with error: reactor already installed.
            if sys.platform in ("cygwin"):
                cmd_options.extend(['--reactor', 'poll'])
        if self.reporter is not None:
            cmd_options.extend(['--reporter', self.reporter])
        if self.rterrors is not None:
            cmd_options.append('--rterrors')
        if self.debug_stacktraces is not None:
            cmd_options.append('--debug-stacktraces')
        config = trial.Options()
        config.parseOptions(cmd_options)


        args = self.test_args
        if type(args) == str:
            args = [args,]

        config['tests'] = args

        if self.coverage:
            config.opt_coverage()

        trial._initialDebugSetup(config)
        trialRunner = trial._makeRunner(config)
        suite = trial._getSuite(config)

        # run the tests
        if self.until_failure:
            test_result = trialRunner.runUntilFailure(suite)
        else:
            test_result = trialRunner.run(suite)

        # write coverage data
        if config.tracer:
            sys.settrace(None)
            results = config.tracer.results()
            results.write_results(show_missing=1, summary=False,
                                  coverdir=config.coverdir)

        if test_result.wasSuccessful():
            sys.exit(0) # success
        else:
            sys.exit(1) # failure



def set_version(version):
    global _version

    _version = version


def get_version():
    v = ''
    prev = None

    for x in _version:
        if prev is not None:
            if isinstance(x, int):
                v += '.'

        prev = x
        v += str(x)

    return v.strip('.')


def extra_setup_args():
    """
    Extra kwargs to supply in the call to C{setup}.

    This is used to supply custom commands, not metadata - that should live in
    setup.py itself.
    """
    return {
        'distclass': MyDistribution,
        'cmdclass': {
            'test': TrialTest,
            'build_ext': MyBuildExt,
            'sdist': MySDist
        }
    }



def get_test_requirements():
    """
    Returns a list of required packages to run the test suite.
    """
    return []



def write_version_py(filename='rtmpy/_version.py'):
    """
    """
    if os.path.exists(filename):
        os.remove(filename)

    content = """\
# THIS FILE IS GENERATED BY RTMPY SETUP.PY
from pyamf.versions import Version

version = Version(*%(version)r)
"""
    a = open(filename, 'wt')

    try:
        a.write(content % {'version': _version})
    finally:
        a.close()



def get_extras_require():
    return {}



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

        print('WARNING: Could not build extension for %r, no source found' % (
            mod_name,))



def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()



def get_extensions():
    """
    Return a list of Extension instances that can be compiled.
    """
    if not can_compile_extensions:
        print(80 * '*')
        print('WARNING:')
        print('\tAn optional code optimization (C extension) could not be compiled.\n\n')
        print('\tOptimizations for this package will not be available!\n\n')
        print('Compiling extensions is not supported on %r' % (sys.platform,))
        print(80 * '*')

        return []

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

    return classifiers + [dev_status()]



def recursive_glob(path, pattern):
    matches = []

    for root, dirnames, filenames in os.walk(path):
        for filename in fnmatch.filter(filenames, pattern):
            matches.append(os.path.normpath(os.path.join(root, filename)))

    return matches



def get_install_requirements():
    """
    Returns a list of dependencies for RTMPy to function correctly on the
    target platform.
    """
    install_requires = ['Twisted>=2.5.0', 'PyAMF>=0.6']

    if sys.platform.startswith('win'):
        install_requires.append('PyWin32')

    if 'dev' in get_version():
        if can_compile_extensions:
            install_requires.extend(['Cython>=0.13'])

    return install_requires



def get_test_requirements():
    """
    Returns a list of required packages to run the test suite.
    """
    test_requires = ['Twisted>=2.5.0', 'PyAMF>=0.6']

    if can_compile_extensions:
        test_requires.extend(['Cython>=0.13'])

    return test_requires



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
