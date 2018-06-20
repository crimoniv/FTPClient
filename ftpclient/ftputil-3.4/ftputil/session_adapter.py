# Copyright (C) 2015, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

"""
Session adapter for `ftplib.FTP`-compatible session factories
to make them usable with ftputil under Python 2.

`ftplib.FTP` under Python 2 doesn't work with unicode strings
that contain non-ASCII characters (see ticket #100). Since ftputil
converts string arguments to unicode strings as soon as possible,
this even affects calls to `ftputil.FTPHost` methods when the string
arguments are byte strings.

ftputil client code
          V
          V
`ftputil.FTPHost` methods
          V
          V
convert byte strings to unicode (inside `FTPHost` methods)
          V
          V
session adapter converts from unicode to byte strings
          V
          V
`ftplib.FTP` (or other session) methods

You may wonder why we convert byte strings to unicode strings in
`ftputil.FTPHost` and unicode strings back to byte strings in the
adapter. To make the string handling in ftputil consistent for Python
2 and 3, ftputil tries to work everywhere with the same string type.
Because the focus of ftputil is on modern Python (i. e. Python 3),
this universal string type is unicode. Indeed the string arguments
for `ftplib.FTP` under Python 3 are all unicode strings.

Having different code for Python 2 and Python 3 all over in ftputil
would be bad for maintainability. (ftputil is complicated enough as it
is.) Therefore, this adapter is the only place to deal with the
preferred string type of `ftplib` under Python 2 vs. Python 3.
"""

from __future__ import unicode_literals

import ftputil.compat
import ftputil.tool


# Shouldn't be used by ftputil client code
__all__ = []


# Shortcut
as_bytes = ftputil.tool.as_bytes


# We only have to adapt the methods that are directly called by
# ftputil and only those that take string arguments.
#
# Keep the call signature of each adaptor method the same as the
# signature of the adapted method so that code that introspects
# the signature of the method still works.

class SessionAdapter(object):

    def __init__(self, session):
        self._session = session

    def voidcmd(self, cmd):
        cmd = as_bytes(cmd)
        return self._session.voidcmd(cmd)

    def transfercmd(self, cmd, rest=None):
        cmd = as_bytes(cmd)
        return self._session.transfercmd(cmd, rest)

    def dir(self, *args):
        # This is somewhat tricky, since some of the args may not
        # be strings. The last argument may be a callback.
        args = list(args)
        for index, arg in enumerate(args):
            # Replace only unicode strings with a corresponding
            # byte string.
            if isinstance(arg, ftputil.compat.unicode_type):
                args[index] = as_bytes(arg)
        return self._session.dir(*args)

    def rename(self, fromname, toname):
        fromname = as_bytes(fromname)
        toname = as_bytes(toname)
        return self._session.rename(fromname, toname)

    def delete(self, filename):
        filename = as_bytes(filename)
        return self._session.delete(filename)

    def cwd(self, dirname):
        dirname = as_bytes(dirname)
        return self._session.cwd(dirname)

    def mkd(self, dirname):
        dirname = as_bytes(dirname)
        return self._session.mkd(dirname)

    def rmd(self, dirname):
        dirname = as_bytes(dirname)
        return self._session.rmd(dirname)

    # Dispatch to session itself for methods that don't need string
    # conversions.
    def __getattr__(self, name):
        return getattr(self._session, name)
