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

import sys
import os.path


try:
    import Cython
    # may need to work around setuptools bug by providing a fake Pyrex
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fake_pyrex"))
except ImportError:
    pass


from distribute_setup import use_setuptools
use_setuptools(download_delay=3)

from setuptools import setup, find_packages

import setupinfo


setup(
    name = "RTMPy",
    url = "http://rtmpy.org",
    version = setupinfo.get_version(),
    author = "The RTMPy Project",
    author_email = "rtmpy-dev@rtmpy.org",
    description = "Twisted protocol for RTMP",
    long_description = open('README.txt', 'rt').read(),
    keywords = setupinfo.keywords,
    packages = find_packages(exclude=["*.tests"]),
    install_requires = setupinfo.get_install_requirements(),
    tests_require = setupinfo.get_test_requirements(),
    test_suite = "rtmpy.tests.get_suite",
    ext_modules = setupinfo.get_extensions(),
    zip_safe = True,
    license = "LGPL 2.1 License",
    platforms = ["any"],
    classifiers = [
        "Framework :: Twisted",
        "Natural Language :: English",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.4",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ] + setupinfo.get_trove_classifiers(),
    **setupinfo.extra_setup_args())
