=====================
 Installation Guide
=====================

.. contents::

RTMPy requires Python_ 2.4 or newer. Python 3.0 isn't supported yet.


Easy Installation
=================

If you have setuptools_ or the `easy_install`_ tool already installed,
simply type the following on the command-line to install RTMPy::

    easy_install rtmpy

`Note: you might need root permissions or equivalent for these steps.`


To upgrade your existing RTMPy installation to the latest version
use::

    easy_install -U rtmpy


Manual Installation
===================

Prerequisites
-------------

The following software packages are prerequisites:

- Twisted_ 2.5 or newer
- PyAMF_ 0.6.2 or newer
- `zope.interface`_ 3.3.0 or newer
- PyWin32_ b210 or newer (for Windows only)

Step 1
------

:doc:`community/download` and unpack the RTMPy archive of your choice::

    tar zxfv RTMPy-<version>.tar.gz
    cd RTMPy-<version>


Step 2
------

Run the Python-typical setup at the top of the source directory
from a command-prompt::

    python setup.py install

This will byte-compile the Python source code and install it in the
``site-packages`` directory of your Python installation.


Unit Tests
==========

To run the RTMPy unit tests the following software packages
must be installed. The ``easy_install`` command will automatically
install them for you, as described above, but you can also choose to
download and install the packages manually.

- unittest2_ (included in Python 2.7 and newer)

You can run the unit tests using setuptools like this::

    python setup.py test

Other libraries for unit testing are also supported, including:

- nose_
- Trial_


Advanced Options
================

To find out about other advanced installation options, run::

    easy_install --help

Also see `Installing Python Modules`_ for detailed information.

To install RTMPy to a custom location::

    easy_install --prefix=/path/to/installdir


Documentation
=============

Sphinx
------

To build the Sphinx documentation you need:

- Sphinx_ 1.0 or newer
- `sphinxcontrib.epydoc`_ 0.4 or newer
- a :doc:`copy <community/download>` of the RTMPy source distribution

Unix users run the command below in the ``rtmpy/doc`` directory to create the
HTML version of the RTMPy documentation::

    make html

Windows users can run the make.bat file instead::

    make.bat

This will generate the HTML documentation in the ``rtmpy/doc/build/html``
folder. This documentation is identical to the content on the main RTMPy
website_.

**Note**: if you don't have the `make` tool installed then you can invoke
Sphinx from the ``rtmpy/doc`` directory directly like this::

    sphinx-build -b html . build

Epydoc
------

To build the Epydoc API documentation you need:

- Epydoc_ 3.0 or newer
- a :doc:`copy <community/download>` of the RTMPy source distribution

Run the command below in the root ``rtmpy`` directory to create the
HTML version of the RTMPy API documentation::

    epydoc --config=setup.cfg

This will generate the HTML documentation in the ``rtmpy/doc/build/api``
folder.


.. _Python: 	    http://www.python.org
.. _setuptools:	    http://peak.telecommunity.com/DevCenter/setuptools
.. _easy_install:   http://peak.telecommunity.com/DevCenter/EasyInstall#installing-easy-install
.. _ez_setup.py:    http://github.com/hydralabs/rtmpy/blob/master/ez_setup.py
.. _Twisted:	    http://twistedmatrix.com
.. _PyAMF: 	    http://pyamf.org
.. _zope.interface: http://pypi.python.org/pypi/zope.interface
.. _PyWin32:	    http://sourceforge.net/projects/pywin32
.. _Epydoc:	    http://epydoc.sourceforge.net
.. _unittest2:	    http://pypi.python.org/pypi/unittest2
.. _nose:	    http://somethingaboutorange.com/mrl/projects/nose
.. _Trial:	    http://twistedmatrix.com/trac/wiki/TwistedTrial
.. _Sphinx:         http://sphinx.pocoo.org
.. _website:        http://rtmpy.org
.. _Installing Python Modules: http://docs.python.org/install/index.html
.. _sphinxcontrib.epydoc: http://packages.python.org/sphinxcontrib-epydoc
