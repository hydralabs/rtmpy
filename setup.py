from ez_setup import use_setuptools

use_setuptools()

from setuptools import setup, find_packages

setup(name = "RTMPy",
    version = "0.0.1",
    description = "RTMP and AMF client/server Twisted implementation",
    url = "http://dev.collab.com/rtmpy",
    packages = find_packages('src'),
    package_dir = {'':'src'},
    license = "MIT License",
    classifiers = [
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ])
