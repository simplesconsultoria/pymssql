#!/usr/bin/env python
#
# setup.py
#
# Copyright (C) 2009 Damien Churchill <damoxc@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.    If not, write to:
#   The Free Software Foundation, Inc.,
#   51 Franklin Street, Fifth Floor
#   Boston, MA    02110-1301, USA.
#

import os
import os.path as osp
import sys
import getpass

sys.path.append(osp.join(osp.dirname(__file__), '.pyrex'))

try:
    from setuptools import setup, Extension
    from setuptools.command.develop import develop as STDevelopCmd
except ImportError:
    import ez_setup
    ez_setup.use_setuptools()
    from setuptools import setup, Extension

from distutils import log
from distutils.cmd import Command
from distutils.command.clean import clean as _clean
from Cython.Distutils import build_ext
import struct

_extra_compile_args = [
    '-DMSDBLIB'
]

ROOT = osp.abspath(osp.dirname(__file__))
WINDOWS = False

# 32 bit or 64 bit system?
BITNESS = struct.calcsize("P") * 8

if sys.platform == 'win32':
    WINDOWS = True
    include_dirs = []
    library_dirs = []
    libraries = []
else:
    FREETDS = osp.join(ROOT, 'freetds', 'nix_%s' % BITNESS)
    include_dirs = [
        osp.join(FREETDS, 'include')
    ]
    library_dirs = [
        osp.join(FREETDS, 'lib')
    ]
    libraries = [
        'sybdb', # on Mandriva you may have to change it to sybdb_mssql
        'rt',
    ]

if sys.platform == 'darwin':
    fink = '/sw/'
    include_dirs.insert(0, fink + 'include')
    library_dirs.insert(0, fink + 'lib')

    # some mac ports paths
    include_dirs += [
        '/opt/local/include',
        '/opt/local/include/freetds',
        '/opt/local/freetds/include'
    ]
    library_dirs += [
        '/opt/local/lib',
        '/opt/local/lib/freetds',
        '/opt/local/freetds/lib'
    ]

# TODO: Still need to remove reliance on this class for win32
class win32_build_ext(build_ext):
    """
    Subclass the Cython build_ext command so we can detect the compiler so we
    can specify the correct command line switches and libraries on the win32
    platform.
    """

    def build_extensions(self):
        global library_dirs, include_dirs, libraries

        from distutils.cygwinccompiler import Mingw32CCompiler
        extra_cc_args = []
        if isinstance(self.compiler, Mingw32CCompiler):
            freetds_dir = 'ming'
            extra_cc_args = [
                '-Wl,-allow-multiple-definition',
                '-Wl,-subsystem,windows-mthreads',
                '-mwindows',
                '-Wl,--strip-all'
            ]
            libraries = [
                'libiconv', 'iconv',
                'sybdb',
                'ws2_32', 'wsock32', 'kernel32',
            ]
        else:
            freetds_dir = 'vs2008'
            libraries = [
                'db-lib', 'tds',
                'ws2_32', 'wsock32', 'kernel32', 'shell32',
            ]

        FREETDS = osp.join(ROOT, 'freetds', '{0}_{1}'.format(freetds_dir, BITNESS))
        for e in self.extensions:
            e.extra_compile_args.extend(extra_cc_args)
            e.libraries.extend(libraries)
            e.include_dirs.append(osp.join(FREETDS, 'include'))
            e.library_dirs.append(osp.join(FREETDS, 'lib'))

        build_ext.build_extensions(self)


class clean(_clean):
    """
    Subclass clean so it removes all generated files.
    """

    def run(self):
        _clean.run(self)
        for ext in self.distribution.ext_modules:
            cy_sources = [s for s in ext.sources if s.endswith('.pyx')]
            for cy_source in cy_sources:
                so_built = cy_source[:-3] + 'so'
                if osp.exists(so_built):
                    log.info('removing %s', so_built)
                    os.remove(so_built)


class release(Command):
    """
    Setuptools command to run all the required commands to perform
    a release. This acts differently depending on the platform it
    is being run on.
    """

    description = "Run all the commands required for a release."

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.username = None
        self.password = None
        self.store = None

        if WINDOWS:
            self.release_windows()
        else:
            self.release_unix()

    def release_windows(self):
        # generate windows source distributions
        sdist = self.distribution.get_command_obj('sdist')
        sdist.formats = 'zip'
        sdist.ensure_finalized()
        sdist.run()

        # generate a windows egg
        self.run_command('bdist_egg')

        # generate windows installers
        bdist = self.reinitialize_command('bdist')
        bdist.formats = 'zip,wininst'
        bdist.ensure_finalized()
        bdist.run()

        (name, version, fullname) = self.get_info()

        self.upload(fullname + '.zip', '%s %s source zipped' % (name, version))
        self.upload(fullname + '.win32.zip', '%s %s win32 zip installer' % (name, version))
        self.upload(fullname + '.win32-py2.6.exe', '%s %s windows installer' % (name, version))
        self.upload(fullname + '-py2.6-win32.egg', '%s %s windows egg' % (name, version))

    def release_unix(self):
        # generate linux source distributions
        sdist = self.distribution.get_command_obj('sdist')
        sdist.formats = 'gztar,bztar'
        sdist.ensure_finalized()
        sdist.run()

        (name, version, fullname) = self.get_info()
        self.upload(fullname + '.tar.gz', '%s %s source gzipped' % (name, version))
        self.upload(fullname + '.tar.bz2', '%s %s source bzipped' % (name, version))

    def get_info(self):
        """
        Return the project name and version
        """
        return (
            self.distribution.get_name(),
            self.distribution.get_version(),
            self.distribution.get_fullname()
        )

    def upload(self, filename, comment):
        from gc_upload import upload

        if self.username is None:
            username = raw_input('Username: ')
            password = getpass.getpass('Password: ')

            if self.store is None:
                store = raw_input('Store credentials for later use? [Y/n]')
                self.store = store in ('', 'y', 'Y')

            if self.store:
                self.username = username
                self.password = password

        else:
            username = self.username
            password = self.password

        filename = osp.join('dist', filename)
        log.info('uploading %s to googlecode', filename)
        (status, reason, url) = upload(filename, 'pymssql', username, password, comment)
        if not url:
            log.error('upload to googlecode failed: %s', reason)


class DevelopCmd(STDevelopCmd):
    def run(self):
        # add in the nose plugin only when we are using the develop command
        self.distribution.entry_points['nose.plugins'] = ['pymssql_config = tests.nose_plugin:ConfigPlugin']
        STDevelopCmd.run(self)


if WINDOWS:
    build_ext_class = win32_build_ext
else:
    build_ext_class = build_ext

setup(
    name  = 'pymssql',
    version = '2.0.0b1',
    description = 'A simple database interface to MS-SQL for Python.',
    long_description = 'A simple database interface to MS-SQL for Python.',
    author = 'Damien Churchill',
    author_email = 'damoxc@gmail.com',
    license = 'LGPL',
    url = 'http://pymssql.sourceforge.net',
    cmdclass = {
        'build_ext': build_ext_class,
        'clean': clean,
        'release': release,
        'develop': DevelopCmd
    },
    data_files = [
        ('', ['_mssql.pyx', 'pymssql.pyx'])
    ],
    zip_safe = False,
    ext_modules = [
        Extension('_mssql', ['_mssql.c'],
            extra_compile_args = _extra_compile_args,
            include_dirs = include_dirs,
            library_dirs = library_dirs,
            libraries = libraries,
        ),
        Extension('pymssql', ['pymssql.c'],
            extra_compile_args = _extra_compile_args,
            include_dirs = include_dirs,
            library_dirs = library_dirs,
            libraries = libraries,
        ),
    ],

    # don't remove this, otherwise the customization above in DevelopCmd
    # will break.  You can safely add to it though, if needed.
    entry_points = {}

)
