# Copyright (C) 2002-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

from __future__ import unicode_literals

import ftplib

import pytest

import ftputil.compat
import ftputil.error

from test import mock_ftplib
from test import test_base


#
# Several customized `MockSession` classes
#
class ReadMockSession(mock_ftplib.MockSession):

    mock_file_content = b"line 1\r\nanother line\r\nyet another line"


class ReadMockSessionWithMoreNewlines(mock_ftplib.MockSession):

    mock_file_content = b"\r\n".join(map(ftputil.compat.bytes_type, range(20)))


class InaccessibleDirSession(mock_ftplib.MockSession):

    _login_dir = "/inaccessible"

    def pwd(self):
        return self._login_dir

    def cwd(self, dir):
        if dir in (self._login_dir, self._login_dir + "/"):
            raise ftplib.error_perm
        else:
            super(InaccessibleDirSession, self).cwd(dir)


class TestFileOperations(object):
    """Test operations with file-like objects."""

    def test_inaccessible_dir(self):
        """Test whether opening a file at an invalid location fails."""
        host = test_base.ftp_host_factory(
                 session_factory=InaccessibleDirSession)
        with pytest.raises(ftputil.error.FTPIOError):
            host.open("/inaccessible/new_file", "w")

    def test_caching(self):
        """Test whether `FTPFile` cache of `FTPHost` object works."""
        host = test_base.ftp_host_factory()
        assert len(host._children) == 0
        path1 = "path1"
        path2 = "path2"
        # Open one file and inspect cache.
        file1 = host.open(path1, "w")
        child1 = host._children[0]
        assert len(host._children) == 1
        assert not child1._file.closed
        # Open another file.
        file2 = host.open(path2, "w")
        child2 = host._children[1]
        assert len(host._children) == 2
        assert not child2._file.closed
        # Close first file.
        file1.close()
        assert len(host._children) == 2
        assert child1._file.closed
        assert not child2._file.closed
        # Re-open first child's file.
        file1 = host.open(path1, "w")
        child1_1 = file1._host
        # Check if it's reused.
        assert child1 is child1_1
        assert not child1._file.closed
        assert not child2._file.closed
        # Close second file.
        file2.close()
        assert child2._file.closed

    def test_write_to_directory(self):
        """Test whether attempting to write to a directory fails."""
        host = test_base.ftp_host_factory()
        with pytest.raises(ftputil.error.FTPIOError):
            host.open("/home/sschwarzer", "w")

    def test_binary_read(self):
        """Read data from a binary file."""
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        with host.open("some_file", "rb") as fobj:
            data = fobj.read()
        assert data == ReadMockSession.mock_file_content

    def test_binary_write(self):
        """Write binary data with `write`."""
        host = test_base.ftp_host_factory()
        data = b"\000a\001b\r\n\002c\003\n\004\r\005"
        with host.open("dummy", "wb") as output:
            output.write(data)
        child_data = mock_ftplib.content_of("dummy")
        expected_data = data
        assert child_data == expected_data

    def test_ascii_read(self):
        """Read ASCII text with plain `read`."""
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        with host.open("dummy", "r") as input_:
            data = input_.read(0)
            assert data == ""
            data = input_.read(3)
            assert data == "lin"
            data = input_.read(7)
            assert data == "e 1\nano"
            data = input_.read()
            assert data == "ther line\nyet another line"
            data = input_.read()
            assert data == ""

    def test_ascii_write(self):
        """Write ASCII text with `write`."""
        host = test_base.ftp_host_factory()
        data = " \nline 2\nline 3"
        with host.open("dummy", "w", newline="\r\n") as output:
            output.write(data)
        child_data = mock_ftplib.content_of("dummy")
        # This corresponds to the byte stream, so expect a `bytes` object.
        expected_data = b" \r\nline 2\r\nline 3"
        assert child_data == expected_data

    # TODO: Add tests with given encoding and possibly buffering.

    def test_ascii_writelines(self):
        """Write ASCII text with `writelines`."""
        host = test_base.ftp_host_factory()
        data = [" \n", "line 2\n", "line 3"]
        backup_data = data[:]
        output = host.open("dummy", "w", newline="\r\n")
        output.writelines(data)
        output.close()
        child_data = mock_ftplib.content_of("dummy")
        expected_data = b" \r\nline 2\r\nline 3"
        assert child_data == expected_data
        # Ensure that the original data was not modified.
        assert data == backup_data

    def test_binary_readline(self):
        """Read binary data with `readline`."""
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        input_ = host.open("dummy", "rb")
        data = input_.readline(3)
        assert data == b"lin"
        data = input_.readline(10)
        assert data == b"e 1\r\n"
        data = input_.readline(13)
        assert data == b"another line\r"
        data = input_.readline()
        assert data == b"\n"
        data = input_.readline()
        assert data == b"yet another line"
        data = input_.readline()
        assert data == b""
        input_.close()

    def test_ascii_readline(self):
        """Read ASCII text with `readline`."""
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        input_ = host.open("dummy", "r")
        data = input_.readline(3)
        assert data == "lin"
        data = input_.readline(10)
        assert data == "e 1\n"
        data = input_.readline(13)
        assert data == "another line\n"
        data = input_.readline()
        assert data == "yet another line"
        data = input_.readline()
        assert data == ""
        input_.close()

    def test_ascii_readlines(self):
        """Read ASCII text with `readlines`."""
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        input_ = host.open("dummy", "r")
        data = input_.read(3)
        assert data == "lin"
        data = input_.readlines()
        assert data == ["e 1\n", "another line\n", "yet another line"]
        input_.close()

    def test_binary_iterator(self):
        """
        Test the iterator interface of `FTPFile` objects (without
        newline conversion.
        """
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        input_ = host.open("dummy", "rb")
        input_iterator = iter(input_)
        assert next(input_iterator) == b"line 1\r\n"
        assert next(input_iterator) == b"another line\r\n"
        assert next(input_iterator) == b"yet another line"
        with pytest.raises(StopIteration):
            input_iterator.__next__()
        input_.close()

    def test_ascii_iterator(self):
        """
        Test the iterator interface of `FTPFile` objects (with newline
        conversion).
        """
        host = test_base.ftp_host_factory(session_factory=ReadMockSession)
        input_ = host.open("dummy")
        input_iterator = iter(input_)
        assert next(input_iterator) == "line 1\n"
        assert next(input_iterator) == "another line\n"
        assert next(input_iterator) == "yet another line"
        with pytest.raises(StopIteration):
            input_iterator.__next__()
        input_.close()

    def test_read_unknown_file(self):
        """Test whether reading a file which isn't there fails."""
        host = test_base.ftp_host_factory()
        with pytest.raises(ftputil.error.FTPIOError):
            host.open("notthere", "r")


class TestAvailableChild(object):

    def _failing_pwd(self, exception_class):
        """
        Return a function that will be used instead of the
        `session.pwd` and will raise the exception
        `exception_to_raise`.
        """
        def new_pwd():
            raise exception_class("")
        return new_pwd

    def _test_with_pwd_error(self, exception_class):
        """
        Test if reusing a child session fails because of
        `child_host._session.pwd` raising an exception of type
        `exception_class`.
        """
        host = test_base.ftp_host_factory()
        # Implicitly create a child session.
        with host.open("/home/older") as _:
            pass
        assert len(host._children) == 1
        # Make sure reusing the previous child session will fail.
        host._children[0]._session.pwd = self._failing_pwd(exception_class)
        # Try to create a new file. Since `pwd` now raises an
        # exception, a new child session should be created.
        with host.open("home/older") as _:
            pass
        assert len(host._children) == 2

    def test_pwd_with_error_temp(self):
        """
        Test if an `error_temp` in `_session.pwd` skips the child
        session.
        """
        self._test_with_pwd_error(ftplib.error_temp)

    def test_pwd_with_error_reply(self):
        """
        Test if an `error_reply` in `_session.pwd` skips the child
        session.
        """
        self._test_with_pwd_error(ftplib.error_reply)

    def test_pwd_with_OSError(self):
        """
        Test if an `OSError` in `_session.pwd` skips the child
        session.
        """
        self._test_with_pwd_error(OSError)

    def test_pwd_with_EOFError(self):
        """
        Test if an `EOFError` in `_session.pwd` skips the child
        session.
        """
        self._test_with_pwd_error(EOFError)
