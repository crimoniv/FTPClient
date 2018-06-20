# Copyright (C) 2003-2014, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

"""
ftputil.error - exception classes and wrappers
"""

# pylint: disable=too-many-ancestors

from __future__ import unicode_literals

import ftplib

import ftputil.tool
import ftputil.version


# You _can_ import these with `from ftputil.error import *`, - but
# it's _not_ recommended.
__all__ = [
  "InternalError",
  "RootDirError",
  "InaccessibleLoginDirError",
  "TimeShiftError",
  "ParserError",
  "KeepAliveError",
  "FTPOSError",
  "TemporaryError",
  "PermanentError",
  "CommandNotImplementedError",
  "SyncError",
  "FTPIOError",
]


class FTPError(Exception):
    """General ftputil error class."""

    # In Python 2, we can't use a keyword argument after `*args`, so
    # `pop` from `**kwargs`.
    def __init__(self, *args, **kwargs):
        super(FTPError, self).__init__(*args)
        if "original_exception" in kwargs:
            # Byte string under Python 2.
            exception_string = str(kwargs.pop("original_exception"))
            self.strerror = ftputil.tool.as_unicode(exception_string)
        elif args:
            # If there was no `original_exception` argument, assume
            # the first argument is a string. It may be a byte string
            # though.
            self.strerror = ftputil.tool.as_unicode(args[0])
        else:
            self.strerror = ""
        try:
            self.errno = int(self.strerror[:3])
        except ValueError:
            # `int()` argument couldn't be converted to an integer.
            self.errno = None
        self.file_name = None

    def __str__(self):
        return "{0}\nDebugging info: {1}".format(self.strerror,
                                                 ftputil.version.version_info)


# Internal errors are those that have more to do with the inner
# workings of ftputil than with errors on the server side.
class InternalError(FTPError):
    """Internal error."""
    pass

class RootDirError(InternalError):
    """Raised for generic stat calls on the remote root directory."""
    pass

class InaccessibleLoginDirError(InternalError):
    """May be raised if the login directory isn't accessible."""
    pass

class TimeShiftError(InternalError):
    """Raised for invalid time shift values."""
    pass

class ParserError(InternalError):
    """Raised if a line of a remote directory can't be parsed."""
    pass

class CacheMissError(InternalError):
    """Raised if a path isn't found in the cache."""
    pass

# Currently not used
class KeepAliveError(InternalError):
    """Raised if the keep-alive feature failed."""
    pass

class FTPOSError(FTPError, OSError):
    """Generic FTP error related to `OSError`."""
    pass

class TemporaryError(FTPOSError):
    """Raised for temporary FTP errors (4xx)."""
    pass

class PermanentError(FTPOSError):
    """Raised for permanent FTP errors (5xx)."""
    pass

class CommandNotImplementedError(PermanentError):
    """Raised if the server doesn't implement a certain feature (502)."""
    pass

class RecursiveLinksError(PermanentError):
    """Raised if an infinite link structure is detected."""
    pass

# Currently not used
class SyncError(PermanentError):
    """Raised for problems specific to syncing directories."""
    pass


class FtplibErrorToFTPOSError(object):
    """
    Context manager to convert `ftplib` exceptions to exceptions
    derived from `FTPOSError`.
    """

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            # No exception
            return
        if isinstance(exc_value, ftplib.error_temp):
            raise TemporaryError(*exc_value.args, original_exception=exc_value)
        elif isinstance(exc_value, ftplib.error_perm):
            # If `exc_value.args[0]` is present, assume it's a byte or
            # unicode string.
            if (
              exc_value.args and
              ftputil.tool.as_unicode(exc_value.args[0]).startswith("502")
            ):
                raise CommandNotImplementedError(*exc_value.args)
            else:
                raise PermanentError(*exc_value.args,
                                     original_exception=exc_value)
        elif isinstance(exc_value, ftplib.all_errors):
            raise FTPOSError(*exc_value.args, original_exception=exc_value)
        else:
            raise

ftplib_error_to_ftp_os_error = FtplibErrorToFTPOSError()


class FTPIOError(FTPError, IOError):
    """Generic FTP error related to `IOError`."""
    pass


class FtplibErrorToFTPIOError(object):
    """
    Context manager to convert `ftplib` exceptions to `FTPIOError`
    exceptions.
    """

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            # No exception
            return
        if isinstance(exc_value, ftplib.all_errors):
            raise FTPIOError(*exc_value.args, original_exception=exc_value)
        else:
            raise

ftplib_error_to_ftp_io_error = FtplibErrorToFTPIOError()
