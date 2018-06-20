# encoding: utf-8
# Copyright (C) 2002-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

from __future__ import unicode_literals

import ftplib

import pytest

import ftputil.error


class TestFTPErrorArguments(object):
    """
    The `*Error` constructors should accept either a byte string or a
    unicode string.
    """

    def test_bytestring_argument(self):
        # An umlaut as latin-1 character
        io_error = ftputil.error.FTPIOError(b"\xe4")
        os_error = ftputil.error.FTPOSError(b"\xe4")

    def test_unicode_argument(self):
        # An umlaut as unicode character
        io_error = ftputil.error.FTPIOError("\xe4")
        os_error = ftputil.error.FTPOSError("\xe4")


class TestErrorConversion(object):

    def callee(self):
        raise ftplib.error_perm()

    def test_ftplib_error_to_ftp_os_error(self):
        """
        Ensure the `ftplib` exception isn't used as `FTPOSError`
        argument.
        """
        with pytest.raises(ftputil.error.FTPOSError) as exc_info:
            with ftputil.error.ftplib_error_to_ftp_os_error:
                self.callee()
        exc = exc_info.value
        assert not (exc.args and 
                    isinstance(exc.args[0], ftplib.error_perm))
        del exc_info

    def test_ftplib_error_to_ftp_os_error_non_ascii_server_message(self):
        """
        Test that we don't get a `UnicodeDecodeError` if the server
        sends a message containing non-ASCII characters.
        """
        # See ticket #77.
        message = \
          ftputil.tool.as_bytes(
            "Não é possível criar um arquivo já existente.")
        with pytest.raises(ftputil.error.PermanentError):
            with ftputil.error.ftplib_error_to_ftp_os_error:
                raise ftplib.error_perm(message)

    def test_ftplib_error_to_ftp_io_error(self):
        """
        Ensure the `ftplib` exception isn't used as `FTPIOError`
        argument.
        """
        with pytest.raises(ftputil.error.FTPIOError) as exc_info:
            with ftputil.error.ftplib_error_to_ftp_io_error:
                self.callee()
        exc = exc_info.value
        assert not (exc.args and
                    isinstance(exc.args[0], ftplib.error_perm))
        del exc_info

    def test_error_message_reuse(self):
        """
        Test if the error message string is retained if the caught
        exception has more than one element in `args`.
        """
        # See ticket #76.
        with pytest.raises(ftputil.error.FTPOSError) as exc_info:
            # Format "host:port" doesn't work.
            host = ftputil.FTPHost("localhost:21", "", "")
        exc = exc_info.value
        # The error message may be different for different Python
        # versions.
        assert (
          "No address associated with hostname" in str(exc) or
          "Name or service not known" in str(exc))
        del exc_info
