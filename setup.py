#!/usr/bin/env python

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

from distribute_setup import use_setuptools

# 15 seconds is far too long ....
use_setuptools(download_delay=3)

# import ordering is important
import setupinfo
from setuptools import setup, find_packages


version = (0, 2, 'dev')

name = "RTMPy"
description = "Twisted protocol for RTMP"
long_description = setupinfo.read('README.txt')
url = "http://rtmpy.org"
author = "The RTMPy Project"
author_email = "rtmpy-dev@rtmpy.org"
license = "LGPL 2.1 License"

classifiers = """
Framework :: Twisted
Natural Language :: English
Intended Audience :: Developers
Intended Audience :: Information Technology"
License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)
Operating System :: OS Independent
Programming Language :: Python
Programming Language :: Python :: 2.4
Programming Language :: Python :: 2.5
Programming Language :: Python :: 2.6
Programming Language :: Python :: 2.7
Topic :: Software Development :: Libraries :: Python Modules
"""

keywords = """
rtmp flv rtmps rtmpe rtmpt rtmpte amf amf0 amf3 flex flash http https
streaming video audio sharedobject webcam record playback pyamf client
flashplayer air actionscript decoder encoder gateway server
"""


def setup_package():
    setupinfo.set_version(version)

    setupinfo.write_version_py()

    setup(
        name=name,
        version=setupinfo.get_version(),
        description=description,
        long_description=long_description,
        url=url,
        author=author,
        author_email=author_email,
        keywords=keywords.strip(),
        license=license,
        packages=find_packages(),
        ext_modules=setupinfo.get_extensions(),
        install_requires=setupinfo.get_install_requirements(),
        tests_requires=setupinfo.get_test_requirements(),
        test_suite="rtmpy",
        zip_safe=True,
        extras_require=setupinfo.get_extras_require(),
        classifiers=(filter(None, classifiers.split('\n')) +
            setupinfo.get_trove_classifiers()),
        **setupinfo.extra_setup_args())


if __name__ == '__main__':
    setup_package()
