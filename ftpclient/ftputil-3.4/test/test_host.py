# encoding: utf-8
# Copyright (C) 2002-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

from __future__ import unicode_literals

import ftplib
import itertools
import os
import pickle
import posixpath
import random
import time
import warnings

import pytest

import ftputil
import ftputil.compat
import ftputil.error
import ftputil.tool
import ftputil.stat

from test import mock_ftplib
from test import test_base


#
# Helper functions to generate random data
#
def random_data(pool, size=10000):
    """
    Return a byte string of characters consisting of those from the
    pool of integer numbers.
    """
    ordinal_list = [random.choice(pool) for i in range(size)]
    return ftputil.compat.bytes_from_ints(ordinal_list)


def ascii_data():
    r"""
    Return a unicode string of "normal" ASCII characters, including `\r`.
    """
    pool = list(range(32, 128))
    # The idea is to have the "\r" converted to "\n" during the later
    # text write and check this conversion.
    pool.append(ord("\r"))
    return ftputil.tool.as_unicode(random_data(pool))


def binary_data():
    """Return a binary character byte string."""
    pool = list(range(0, 256))
    return random_data(pool)


#
# Several customized `MockSession` classes
#
class FailOnLoginSession(mock_ftplib.MockSession):

    def __init__(self, host="", user="", password=""):
        raise ftplib.error_perm


class FailOnKeepAliveSession(mock_ftplib.MockSession):

    def pwd(self):
        # Raise exception on second call to let the constructor work.
        if not hasattr(self, "pwd_called"):
            self.pwd_called = True
            return "/home"
        else:
            raise ftplib.error_temp


class UnnormalizedCurrentWorkingDirectory(mock_ftplib.MockSession):

    def pwd(self):
        # Deliberately return the current working directory with a
        # trailing slash to test if it's removed when stored in the
        # `FTPHost` instance.
        return "/home/"


class RecursiveListingForDotAsPathSession(mock_ftplib.MockSession):

    dir_contents = {
      ".": """\
lrwxrwxrwx   1 staff          7 Aug 13  2003 bin -> usr/bin

dev:
total 10

etc:
total 10

pub:
total 4
-rw-r--r--   1 staff         74 Sep 25  2000 .message
----------   1 staff          0 Aug 16  2003 .notar
drwxr-xr-x  12 ftp          512 Nov 23  2008 freeware

usr:
total 4""",

      "": """\
total 10
lrwxrwxrwx   1 staff          7 Aug 13  2003 bin -> usr/bin
d--x--x--x   2 staff        512 Sep 24  2000 dev
d--x--x--x   3 staff        512 Sep 25  2000 etc
dr-xr-xr-x   3 staff        512 Oct  3  2000 pub
d--x--x--x   5 staff        512 Oct  3  2000 usr"""}

    def _transform_path(self, path):
        return path


class BinaryDownloadMockSession(mock_ftplib.MockUnixFormatSession):

    mock_file_content = binary_data()


class TimeShiftMockSession(mock_ftplib.MockSession):

    def delete(self, file_name):
        pass

#
# Customized `FTPHost` class for conditional upload/download tests
# and time shift tests
#
class FailingUploadAndDownloadFTPHost(ftputil.FTPHost):

    def upload(self, source, target, mode=""):
        pytest.fail("`FTPHost.upload` should not have been called")

    def download(self, source, target, mode=""):
        pytest.fail("`FTPHost.download` should not have been called")


class TimeShiftFTPHost(ftputil.FTPHost):

    class _Path:
        def split(self, path):
            return posixpath.split(path)
        def set_mtime(self, mtime):
            self._mtime = mtime
        def getmtime(self, file_name):
            return self._mtime
        def join(self, *args):
            return posixpath.join(*args)
        def normpath(self, path):
            return posixpath.normpath(path)
        def isabs(self, path):
            return posixpath.isabs(path)
        def abspath(self, path):
            return "/home/sschwarzer/_ftputil_sync_"
        # Needed for `isdir` in `FTPHost.remove`
        def isfile(self, path):
            return True

    def __init__(self, *args, **kwargs):
        ftputil.FTPHost.__init__(self, *args, **kwargs)
        self.path = self._Path()

#
# Test cases
#
class TestConstructor(object):
    """
    Test initialization of `FTPHost` objects.
    """

    def test_open_and_close(self):
        """
        Test if opening and closing an `FTPHost` object works as
        expected.
        """
        host = test_base.ftp_host_factory()
        host.close()
        assert host.closed is True
        assert host._children == []

    def test_invalid_login(self):
        """Login to invalid host must fail."""
        with pytest.raises(ftputil.error.FTPOSError):
            test_base.ftp_host_factory(FailOnLoginSession)

    def test_pwd_normalization(self):
        """
        Test if the stored current directory is normalized.
        """
        host = test_base.ftp_host_factory(UnnormalizedCurrentWorkingDirectory)
        assert host.getcwd() == "/home"


class TestKeepAlive(object):

    def test_succeeding_keep_alive(self):
        """Assume the connection is still alive."""
        host = test_base.ftp_host_factory()
        host.keep_alive()

    def test_failing_keep_alive(self):
        """Assume the connection has timed out, so `keep_alive` fails."""
        host = test_base.ftp_host_factory(
                 session_factory=FailOnKeepAliveSession)
        with pytest.raises(ftputil.error.TemporaryError):
            host.keep_alive()


class TestSetParser(object):

    class TrivialParser(ftputil.stat.Parser):
        """
        An instance of this parser always returns the same result
        from its `parse_line` method. This is all we need to check
        if ftputil uses the set parser. No actual parsing code is
        required here.
        """

        def __init__(self):
            # We can't use `os.stat("/home")` directly because we
            # later need the object's `_st_name` attribute, which
            # we can't set on a `os.stat` stat value.
            default_stat_result = ftputil.stat.StatResult(os.stat("/home"))
            default_stat_result._st_name = "home"
            self.default_stat_result = default_stat_result

        def parse_line(self, line, time_shift=0.0):
            return self.default_stat_result

    def test_set_parser(self):
        """Test if the selected parser is used."""
        host = test_base.ftp_host_factory()
        assert host._stat._allow_parser_switching is True
        trivial_parser = TestSetParser.TrivialParser()
        host.set_parser(trivial_parser)
        stat_result = host.stat("/home")
        assert stat_result == trivial_parser.default_stat_result
        assert host._stat._allow_parser_switching is False


class TestCommandNotImplementedError(object):

    def test_command_not_implemented_error(self):
        """
        Test if we get the anticipated exception if a command isn't
        implemented by the server.
        """
        host = test_base.ftp_host_factory()
        with pytest.raises(ftputil.error.CommandNotImplementedError):
            host.chmod("nonexistent", 0o644)
        # `CommandNotImplementedError` is a subclass of `PermanentError`.
        with pytest.raises(ftputil.error.PermanentError):
            host.chmod("nonexistent", 0o644)


class TestRecursiveListingForDotAsPath(object):
    """
    Return a recursive directory listing when the path to list
    is a dot. This is used to test for issue #33, see
    http://ftputil.sschwarzer.net/trac/ticket/33 .
    """

    def test_recursive_listing(self):
        host = test_base.ftp_host_factory(
                 session_factory=RecursiveListingForDotAsPathSession)
        lines = host._dir(host.curdir)
        assert lines[0] == "total 10"
        assert lines[1].startswith("lrwxrwxrwx   1 staff")
        assert lines[2].startswith("d--x--x--x   2 staff")
        host.close()

    def test_plain_listing(self):
        host = test_base.ftp_host_factory(
                 session_factory=RecursiveListingForDotAsPathSession)
        lines = host._dir("")
        assert lines[0] == "total 10"
        assert lines[1].startswith("lrwxrwxrwx   1 staff")
        assert lines[2].startswith("d--x--x--x   2 staff")
        host.close()

    def test_empty_string_instead_of_dot_workaround(self):
        host = test_base.ftp_host_factory(
                 session_factory=RecursiveListingForDotAsPathSession)
        files = host.listdir(host.curdir)
        assert files == ["bin", "dev", "etc", "pub", "usr"]
        host.close()


class TestUploadAndDownload(object):
    """Test ASCII upload and binary download as examples."""

    def generate_file(self, data, file_name):
        """Generate a local data file."""
        with open(file_name, "wb") as source_file:
            source_file.write(data)

    def test_download(self):
        """Test mode download."""
        local_target = "_test_target_"
        host = test_base.ftp_host_factory(
                 session_factory=BinaryDownloadMockSession)
        # Download
        host.download("dummy", local_target)
        # Read file and compare
        with open(local_target, "rb") as fobj:
            data = fobj.read()
        remote_file_content = mock_ftplib.content_of("dummy")
        assert data == remote_file_content
        # Clean up
        os.unlink(local_target)

    def test_conditional_upload(self):
        """Test conditional upload."""
        local_source = "_test_source_"
        data = binary_data()
        self.generate_file(data, local_source)
        # Target is newer, so don't upload.
        host = test_base.ftp_host_factory(
                 ftp_host_class=FailingUploadAndDownloadFTPHost)
        flag = host.upload_if_newer(local_source, "/home/newer")
        assert flag is False
        # Target is older, so upload.
        host = test_base.ftp_host_factory()
        flag = host.upload_if_newer(local_source, "/home/older")
        assert flag is True
        remote_file_content = mock_ftplib.content_of("older")
        assert data == remote_file_content
        # Target doesn't exist, so upload.
        host = test_base.ftp_host_factory()
        flag = host.upload_if_newer(local_source, "/home/notthere")
        assert flag is True
        remote_file_content = mock_ftplib.content_of("notthere")
        assert data == remote_file_content
        # Clean up.
        os.unlink(local_source)

    def compare_and_delete_downloaded_data(self, file_name):
        """
        Compare content of downloaded file with its source, then
        delete the local target file.
        """
        with open(file_name, "rb") as fobj:
            data = fobj.read()
        # The name `newer` is used by all callers, so use it here, too.
        remote_file_content = mock_ftplib.content_of("newer")
        assert data == remote_file_content
        # Clean up
        os.unlink(file_name)

    def test_conditional_download_without_target(self):
        """
        Test conditional binary mode download when no target file
        exists.
        """
        local_target = "_test_target_"
        # Target does not exist, so download.
        host = test_base.ftp_host_factory(
                 session_factory=BinaryDownloadMockSession)
        flag = host.download_if_newer("/home/newer", local_target)
        assert flag is True
        self.compare_and_delete_downloaded_data(local_target)

    def test_conditional_download_with_older_target(self):
        """Test conditional binary mode download with newer source file."""
        local_target = "_test_target_"
        # Make target file.
        open(local_target, "w").close()
        # Source is newer (date in 2020), so download.
        host = test_base.ftp_host_factory(
                 session_factory=BinaryDownloadMockSession)
        flag = host.download_if_newer("/home/newer", local_target)
        assert flag is True
        self.compare_and_delete_downloaded_data(local_target)

    def test_conditional_download_with_newer_target(self):
        """Test conditional binary mode download with older source file."""
        local_target = "_test_target_"
        # Make target file.
        open(local_target, "w").close()
        # Source is older (date in 1970), so don't download.
        host = test_base.ftp_host_factory(
                 ftp_host_class=FailingUploadAndDownloadFTPHost,
                 session_factory=BinaryDownloadMockSession)
        flag = host.download_if_newer("/home/older", local_target)
        assert flag is False
        # Remove target file
        os.unlink(local_target)


class TestTimeShift(object):

    def test_rounded_time_shift(self):
        """Test if time shift is rounded correctly."""
        host = test_base.ftp_host_factory(session_factory=TimeShiftMockSession)
        # Use private bound method.
        rounded_time_shift = host._FTPHost__rounded_time_shift
        # Pairs consisting of original value and expected result
        test_data = [
          (      0,           0),
          (      0.1,         0),
          (     -0.1,         0),
          (   1500,        1800),
          (  -1500,       -1800),
          (   1800,        1800),
          (  -1800,       -1800),
          (   2000,        1800),
          (  -2000,       -1800),
          ( 5*3600-100,  5*3600),
          (-5*3600+100, -5*3600)]
        for time_shift, expected_time_shift in test_data:
            calculated_time_shift = rounded_time_shift(time_shift)
            assert calculated_time_shift == expected_time_shift

    def test_assert_valid_time_shift(self):
        """Test time shift sanity checks."""
        host = test_base.ftp_host_factory(session_factory=TimeShiftMockSession)
        # Use private bound method.
        assert_time_shift = host._FTPHost__assert_valid_time_shift
        # Valid time shifts
        test_data = [23*3600, -23*3600, 3600+30, -3600+30]
        for time_shift in test_data:
            assert assert_time_shift(time_shift) is None
        # Invalid time shift (exceeds one day)
        with pytest.raises(ftputil.error.TimeShiftError):
            assert_time_shift(25*3600)
        with pytest.raises(ftputil.error.TimeShiftError):
            assert_time_shift(-25*3600)
        # Invalid time shift (too large deviation from 15-minute units
        # is unacceptable)
        with pytest.raises(ftputil.error.TimeShiftError):
            assert_time_shift(8*60)
        with pytest.raises(ftputil.error.TimeShiftError):
            assert_time_shift(-3600-8*60)

    def test_synchronize_times(self):
        """Test time synchronization with server."""
        host = test_base.ftp_host_factory(ftp_host_class=TimeShiftFTPHost,
                                          session_factory=TimeShiftMockSession)
        # Valid time shifts
        test_data = [
          (60*60+30,  60*60),
          (60*60-100, 60*60),
          (30*60+100, 30*60),
          (45*60-100, 45*60),
        ]
        for measured_time_shift, expected_time_shift in test_data:
            host.path.set_mtime(time.time() + measured_time_shift)
            host.synchronize_times()
            assert host.time_shift() == expected_time_shift
        # Invalid time shifts
        measured_time_shifts = [60*60+8*60, 45*60-6*60]
        for measured_time_shift in measured_time_shifts:
            host.path.set_mtime(time.time() + measured_time_shift)
            with pytest.raises(ftputil.error.TimeShiftError):
                host.synchronize_times()

    def test_synchronize_times_for_server_in_east(self):
        """Test for timestamp correction (see ticket #55)."""
        host = test_base.ftp_host_factory(ftp_host_class=TimeShiftFTPHost,
                                          session_factory=TimeShiftMockSession)
        # Set this explicitly to emphasize the problem.
        host.set_time_shift(0.0)
        hour = 60 * 60
        # This could be any negative time shift.
        presumed_time_shift = -6 * hour
        # Set `mtime` to simulate a server east of us.
        # In case the `time_shift` value for this host instance is 0.0
        # (as is to be expected before the time shift is determined),
        # the directory parser (more specifically
        # `ftputil.stat.Parser.parse_unix_time`) will return a time which
        # is a year too far in the past. The `synchronize_times`
        # method needs to deal with this and add the year "back".
        # I don't think it's a bug in `parse_unix_time` because the
        # method should work once the time shift is set correctly.
        local_time = time.localtime()
        local_time_with_wrong_year = (local_time.tm_year-1,) + local_time[1:]
        presumed_server_time = \
          time.mktime(local_time_with_wrong_year) + presumed_time_shift
        host.path.set_mtime(presumed_server_time)
        host.synchronize_times()
        assert host.time_shift() == presumed_time_shift


class TestAcceptEitherUnicodeOrBytes(object):
    """
    Test whether certain `FTPHost` methods accept either unicode
    or byte strings for the path(s).
    """

    def setup_method(self, method):
        self.host = test_base.ftp_host_factory()

    def test_upload(self):
        """Test whether `upload` accepts either unicode or bytes."""
        host = self.host
        # The source file needs to be present in the current directory.
        host.upload("Makefile", "target")
        host.upload("Makefile", ftputil.tool.as_bytes("target"))

    def test_download(self):
        """Test whether `download` accepts either unicode or bytes."""
        host = test_base.ftp_host_factory(
                 session_factory=BinaryDownloadMockSession)
        local_file_name = "_local_target_"
        host.download("source", local_file_name)
        host.download(ftputil.tool.as_bytes("source"), local_file_name)
        os.remove(local_file_name)

    def test_rename(self):
        """Test whether `rename` accepts either unicode or bytes."""
        # It's possible to mix argument types, as for `os.rename`.
        path_as_unicode = "/home/file_name_test/ä"
        path_as_bytes = ftputil.tool.as_bytes(path_as_unicode)
        paths = [path_as_unicode, path_as_bytes]
        for source_path, target_path in itertools.product(paths, paths):
            self.host.rename(source_path, target_path)

    def test_listdir(self):
        """Test whether `listdir` accepts either unicode or bytes."""
        host = self.host
        as_bytes = ftputil.tool.as_bytes
        host.chdir("/home/file_name_test")
        # Unicode
        items = host.listdir("ä")
        assert items == ["ö", "o"]
        #  Need explicit type check for Python 2
        for item in items:
            assert isinstance(item, ftputil.compat.unicode_type)
        # Bytes
        items = host.listdir(as_bytes("ä"))
        assert items == [as_bytes("ö"), as_bytes("o")]
        #  Need explicit type check for Python 2
        for item in items:
            assert isinstance(item, ftputil.compat.bytes_type)

    def test_chmod(self):
        """Test whether `chmod` accepts either unicode or bytes."""
        host = self.host
        # The `voidcmd` implementation in `MockSession` would raise an
        # exception for the `CHMOD` command.
        host._session.voidcmd = host._session._ignore_arguments
        path = "/home/file_name_test/ä"
        host.chmod(path, 0o755)
        host.chmod(ftputil.tool.as_bytes(path), 0o755)

    def _test_method_with_single_path_argument(self, method, path):
        method(path)
        method(ftputil.tool.as_bytes(path))

    def test_chdir(self):
        """Test whether `chdir` accepts either unicode or bytes."""
        self._test_method_with_single_path_argument(
          self.host.chdir, "/home/file_name_test/ö")

    def test_mkdir(self):
        """Test whether `mkdir` accepts either unicode or bytes."""
        # This directory exists already in the mock session, but this
        # shouldn't matter for the test.
        self._test_method_with_single_path_argument(
          self.host.mkdir, "/home/file_name_test/ä")

    def test_makedirs(self):
        """Test whether `makedirs` accepts either unicode or bytes."""
        self._test_method_with_single_path_argument(
          self.host.makedirs, "/home/file_name_test/ä")

    def test_rmdir(self):
        """Test whether `rmdir` accepts either unicode or bytes."""
        empty_directory_as_required_by_rmdir = "/home/file_name_test/empty_ä"
        self._test_method_with_single_path_argument(
          self.host.rmdir, empty_directory_as_required_by_rmdir)

    def test_remove(self):
        """Test whether `remove` accepts either unicode or bytes."""
        self._test_method_with_single_path_argument(
          self.host.remove, "/home/file_name_test/ö")

    def test_rmtree(self):
        """Test whether `rmtree` accepts either unicode or bytes."""
        empty_directory_as_required_by_rmtree = "/home/file_name_test/empty_ä"
        self._test_method_with_single_path_argument(
          self.host.rmtree, empty_directory_as_required_by_rmtree)

    def test_lstat(self):
        """Test whether `lstat` accepts either unicode or bytes."""
        self._test_method_with_single_path_argument(
          self.host.lstat, "/home/file_name_test/ä")

    def test_stat(self):
        """Test whether `stat` accepts either unicode or bytes."""
        self._test_method_with_single_path_argument(
          self.host.stat, "/home/file_name_test/ä")

    def test_walk(self):
        """Test whether `walk` accepts either unicode or bytes."""
        # We're not interested in the return value of `walk`.
        self._test_method_with_single_path_argument(
          self.host.walk, "/home/file_name_test/ä")


class TestFailingPickling(object):

    def test_failing_pickling(self):
        """Test if pickling (intentionally) isn't supported."""
        with test_base.ftp_host_factory() as host:
            with pytest.raises(TypeError):
                pickle.dumps(host)
            with host.open("/home/sschwarzer/index.html") as file_obj:
                with pytest.raises(TypeError):
                    pickle.dumps(file_obj)
