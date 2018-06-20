# encoding: UTF-8
# Copyright (C) 2003-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

# Execute tests on a real FTP server (other tests use a mock server).
#
# This test writes some files and directories on the local client and
# the remote server. You'll need write access in the login directory.
# This test can take a few minutes because it has to wait to test the
# timezone calculation.

from __future__ import absolute_import
from __future__ import unicode_literals

import ftplib
import functools
import gc
import operator
import os
import time
import stat

import pytest

import ftputil.compat
import ftputil.error
import ftputil.file_transfer
import ftputil.session
import ftputil.stat_cache

import test


def utc_local_time_shift():
    """
    Return the expected time shift in seconds assuming the server
    uses UTC in its listings and the client uses local time.

    This is needed because Pure-FTPd meanwhile seems to insist that
    the displayed time for files is in UTC.
    """
    utc_tuple = time.gmtime()
    localtime_tuple = time.localtime()
    # To calculate the correct times shift, we need to ignore the
    # DST component in the localtime tuple, i. e. set it to 0.
    localtime_tuple = localtime_tuple[:-1] + (0,)
    time_shift_in_seconds = (time.mktime(utc_tuple) -
                             time.mktime(localtime_tuple))
    # To be safe, round the above value to units of 3600 s (1 hour).
    return round(time_shift_in_seconds / 3600.0) * 3600

# Difference between local times of server and client. If 0.0, server
# and client use the same timezone.
#EXPECTED_TIME_SHIFT = utc_local_time_shift()
# Pure-FTPd seems to have changed its mind (see docstring of
# `utc_local_time_shift`).
EXPECTED_TIME_SHIFT = 0.0


class Cleaner(object):
    """
    This class helps remove directories and files which might
    otherwise be left behind if a test fails in unexpected ways.
    """

    def __init__(self, host):
        # The test class (probably `RealFTPTest`) and the helper
        # class share the same `FTPHost` object.
        self._host = host
        self._ftp_items = []

    def add_dir(self, path):
        """Schedule a directory with path `path` for removal."""
        self._ftp_items.append(("d", self._host.path.abspath(path)))

    def add_file(self, path):
        """Schedule a file with path `path` for removal."""
        self._ftp_items.append(("f", self._host.path.abspath(path)))

    def clean(self):
        """
        Remove the directories and files previously remembered.
        The removal works in reverse order of the scheduling with
        `add_dir` and `add_file`.

        Errors due to a removal are ignored.
        """
        self._host.chdir("/")
        for type_, path in reversed(self._ftp_items):
            try:
                if type_ == "d":
                    # If something goes wrong in `rmtree` we might
                    # leave a mess behind.
                    self._host.rmtree(path)
                elif type_ == "f":
                    # Minor mess if `remove` fails
                    self._host.remove(path)
            except ftputil.error.FTPError:
                pass


class RealFTPTest(object):

    def setup_method(self, method):
        # Server, username, password.
        self.login_data = ("localhost", "ftptest",
                            "d605581757de5eb56d568a4419f4126e")
        self.host = ftputil.FTPHost(*self.login_data)
        self.cleaner = Cleaner(self.host)

    def teardown_method(self, method):
        self.cleaner.clean()
        self.host.close()

    #
    # Helper methods
    #
    def make_remote_file(self, path):
        """Create a file on the FTP host."""
        self.cleaner.add_file(path)
        with self.host.open(path, "wb") as file_:
            # Write something. Otherwise the FTP server might not update
            # the time of last modification if the file existed before.
            file_.write(b"\n")

    def make_local_file(self):
        """Create a file on the local host (= on the client side)."""
        with open("_local_file_", "wb") as fobj:
            fobj.write(b"abc\x12\x34def\t")


class TestMkdir(RealFTPTest):

    def test_mkdir_rmdir(self):
        host = self.host
        dir_name = "_testdir_"
        file_name = host.path.join(dir_name, "_nonempty_")
        self.cleaner.add_dir(dir_name)
        # Make dir and check if the directory is there.
        host.mkdir(dir_name)
        files = host.listdir(host.curdir)
        assert dir_name in files
        # Try to remove a non-empty directory.
        self.cleaner.add_file(file_name)
        non_empty = host.open(file_name, "w")
        non_empty.close()
        with pytest.raises(ftputil.error.PermanentError):
            host.rmdir(dir_name)
        # Remove file.
        host.unlink(file_name)
        # `remove` on a directory should fail.
        try:
            try:
                host.remove(dir_name)
            except ftputil.error.PermanentError as exc:
                assert str(exc).startswith(
                         "remove/unlink can only delete files")
            else:
                pytest.fail("we shouldn't have come here")
        finally:
            # Delete empty directory.
            host.rmdir(dir_name)
        files = host.listdir(host.curdir)
        assert dir_name not in files

    def test_makedirs_without_existing_dirs(self):
        host = self.host
        # No `_dir1_` yet
        assert "_dir1_" not in host.listdir(host.curdir)
        # Vanilla case, all should go well.
        host.makedirs("_dir1_/dir2/dir3/dir4")
        self.cleaner.add_dir("_dir1_")
        # Check host.
        assert host.path.isdir("_dir1_")
        assert host.path.isdir("_dir1_/dir2")
        assert host.path.isdir("_dir1_/dir2/dir3")
        assert host.path.isdir("_dir1_/dir2/dir3/dir4")

    def test_makedirs_from_non_root_directory(self):
        # This is a testcase for issue #22, see
        # http://ftputil.sschwarzer.net/trac/ticket/22 .
        host = self.host
        # No `_dir1_` and `_dir2_` yet
        assert "_dir1_" not in host.listdir(host.curdir)
        assert "_dir2_" not in host.listdir(host.curdir)
        # Part 1: Try to make directories starting from `_dir1_` and
        # change to non-root directory.
        self.cleaner.add_dir("_dir1_")
        host.mkdir("_dir1_")
        host.chdir("_dir1_")
        host.makedirs("_dir2_/_dir3_")
        # Test for expected directory hierarchy.
        assert host.path.isdir("/_dir1_")
        assert host.path.isdir("/_dir1_/_dir2_")
        assert host.path.isdir("/_dir1_/_dir2_/_dir3_")
        assert not host.path.isdir("/_dir1_/_dir1_")
        # Remove all but the directory we're in.
        host.rmdir("/_dir1_/_dir2_/_dir3_")
        host.rmdir("/_dir1_/_dir2_")
        # Part 2: Try to make directories starting from root.
        self.cleaner.add_dir("/_dir2_")
        host.makedirs("/_dir2_/_dir3_")
        # Test for expected directory hierarchy
        assert host.path.isdir("/_dir2_")
        assert host.path.isdir("/_dir2_/_dir3_")
        assert not host.path.isdir("/_dir1_/_dir2_")

    def test_makedirs_of_existing_directory(self):
        host = self.host
        # The (chrooted) login directory
        host.makedirs("/")

    def test_makedirs_with_file_in_the_way(self):
        host = self.host
        self.cleaner.add_dir("_dir1_")
        host.mkdir("_dir1_")
        self.make_remote_file("_dir1_/file1")
        # Try it.
        with pytest.raises(ftputil.error.PermanentError):
            host.makedirs("_dir1_/file1")
        with pytest.raises(ftputil.error.PermanentError):
            host.makedirs("_dir1_/file1/dir2")

    def test_makedirs_with_existing_directory(self):
        host = self.host
        self.cleaner.add_dir("_dir1_")
        host.mkdir("_dir1_")
        host.makedirs("_dir1_/dir2")
        # Check
        assert host.path.isdir("_dir1_")
        assert host.path.isdir("_dir1_/dir2")

    def test_makedirs_in_non_writable_directory(self):
        host = self.host
        # Preparation: `rootdir1` exists but is only writable by root.
        with pytest.raises(ftputil.error.PermanentError):
            host.makedirs("rootdir1/dir2")

    def test_makedirs_with_writable_directory_at_end(self):
        host = self.host
        self.cleaner.add_dir("rootdir2/dir2")
        # Preparation: `rootdir2` exists but is only writable by root.
        # `dir2` is writable by regular ftp users. Both directories
        # below should work.
        host.makedirs("rootdir2/dir2")
        host.makedirs("rootdir2/dir2/dir3")


class TestRemoval(RealFTPTest):

    def test_rmtree_without_error_handler(self):
        host = self.host
        # Build a tree.
        self.cleaner.add_dir("_dir1_")
        host.makedirs("_dir1_/dir2")
        self.make_remote_file("_dir1_/file1")
        self.make_remote_file("_dir1_/file2")
        self.make_remote_file("_dir1_/dir2/file3")
        self.make_remote_file("_dir1_/dir2/file4")
        # Try to remove a _file_ with `rmtree`.
        with pytest.raises(ftputil.error.PermanentError):
            host.rmtree("_dir1_/file2")
        # Remove `dir2`.
        host.rmtree("_dir1_/dir2")
        assert not host.path.exists("_dir1_/dir2")
        assert host.path.exists("_dir1_/file2")
        # Re-create `dir2` and remove `_dir1_`.
        host.mkdir("_dir1_/dir2")
        self.make_remote_file("_dir1_/dir2/file3")
        self.make_remote_file("_dir1_/dir2/file4")
        host.rmtree("_dir1_")
        assert not host.path.exists("_dir1_")

    def test_rmtree_with_error_handler(self):
        host = self.host
        self.cleaner.add_dir("_dir1_")
        host.mkdir("_dir1_")
        self.make_remote_file("_dir1_/file1")
        # Prepare error "handler"
        log = []
        def error_handler(*args):
            log.append(args)
        # Try to remove a file as root "directory".
        host.rmtree("_dir1_/file1", ignore_errors=True, onerror=error_handler)
        assert log == []
        host.rmtree("_dir1_/file1", ignore_errors=False, onerror=error_handler)
        assert log[0][0] == host.listdir
        assert log[0][1] == "_dir1_/file1"
        assert log[1][0] == host.rmdir
        assert log[1][1] == "_dir1_/file1"
        host.rmtree("_dir1_")
        # Try to remove a non-existent directory.
        del log[:]
        host.rmtree("_dir1_", ignore_errors=False, onerror=error_handler)
        assert log[0][0] == host.listdir
        assert log[0][1] == "_dir1_"
        assert log[1][0] == host.rmdir
        assert log[1][1] == "_dir1_"

    def test_remove_non_existent_item(self):
        host = self.host
        with pytest.raises(ftputil.error.PermanentError):
            host.remove("nonexistent")

    def test_remove_existing_file(self):
        self.cleaner.add_file("_testfile_")
        self.make_remote_file("_testfile_")
        host = self.host
        assert host.path.isfile("_testfile_")
        host.remove("_testfile_")
        assert not host.path.exists("_testfile_")


class TestWalk(RealFTPTest):
    """
    Walk the directory tree

      walk_test
      ├── dir1
      │   ├── dir11
      │   └── dir12
      │       ├── dir123
      │       │   └── file1234
      │       ├── file121
      │       └── file122
      ├── dir2
      ├── dir3
      │   ├── dir31
      │   ├── dir32 -> ../dir1/dir12/dir123
      │   ├── file31
      │   └── file32
      └── file4

    and check if the results are the expected ones.
    """

    def _walk_test(self, expected_result, **walk_kwargs):
        """Walk the directory and test results."""
        # Collect data using `walk`.
        actual_result = []
        for items in self.host.walk(**walk_kwargs):
            actual_result.append(items)
        # Compare with expected results.
        assert len(actual_result) == len(expected_result)
        for index, _ in enumerate(actual_result):
            assert actual_result[index] == expected_result[index]

    def test_walk_topdown(self):
        # Preparation: build tree in directory `walk_test`.
        expected_result = [
          ("walk_test",
           ["dir1", "dir2", "dir3"],
           ["file4"]),
          #
          ("walk_test/dir1",
           ["dir11", "dir12"],
           []),
          #
          ("walk_test/dir1/dir11",
           [],
           []),
          #
          ("walk_test/dir1/dir12",
           ["dir123"],
           ["file121", "file122"]),
          #
          ("walk_test/dir1/dir12/dir123",
           [],
           ["file1234"]),
          #
          ("walk_test/dir2",
           [],
           []),
          #
          ("walk_test/dir3",
           ["dir31", "dir32"],
           ["file31", "file32"]),
          #
          ("walk_test/dir3/dir31",
           [],
           []),
          ]
        self._walk_test(expected_result, top="walk_test")

    def test_walk_depth_first(self):
        # Preparation: build tree in directory `walk_test`
        expected_result = [
          ("walk_test/dir1/dir11",
           [],
           []),
          #
          ("walk_test/dir1/dir12/dir123",
           [],
           ["file1234"]),
          #
          ("walk_test/dir1/dir12",
           ["dir123"],
           ["file121", "file122"]),
          #
          ("walk_test/dir1",
           ["dir11", "dir12"],
           []),
          #
          ("walk_test/dir2",
           [],
           []),
          #
          ("walk_test/dir3/dir31",
           [],
           []),
          #
          ("walk_test/dir3",
           ["dir31", "dir32"],
           ["file31", "file32"]),
          #
          ("walk_test",
           ["dir1", "dir2", "dir3"],
           ["file4"])
          ]
        self._walk_test(expected_result, top="walk_test", topdown=False)

    def test_walk_following_links(self):
        # Preparation: build tree in directory `walk_test`.
        expected_result = [
          ("walk_test",
           ["dir1", "dir2", "dir3"],
           ["file4"]),
          #
          ("walk_test/dir1",
           ["dir11", "dir12"],
           []),
          #
          ("walk_test/dir1/dir11",
           [],
           []),
          #
          ("walk_test/dir1/dir12",
           ["dir123"],
           ["file121", "file122"]),
          #
          ("walk_test/dir1/dir12/dir123",
           [],
           ["file1234"]),
          #
          ("walk_test/dir2",
           [],
           []),
          #
          ("walk_test/dir3",
           ["dir31", "dir32"],
           ["file31", "file32"]),
          #
          ("walk_test/dir3/dir31",
           [],
           []),
          #
          ("walk_test/dir3/dir32",
           [],
           ["file1234"]),
          ]
        self._walk_test(expected_result, top="walk_test", followlinks=True)


class TestRename(RealFTPTest):

    def test_rename(self):
        host = self.host
        # Make sure the target of the renaming operation is removed.
        self.cleaner.add_file("_testfile2_")
        self.make_remote_file("_testfile1_")
        host.rename("_testfile1_", "_testfile2_")
        assert not host.path.exists("_testfile1_")
        assert host.path.exists("_testfile2_")

    def test_rename_with_spaces_in_directory(self):
        host = self.host
        dir_name = "_dir with spaces_"
        self.cleaner.add_dir(dir_name)
        host.mkdir(dir_name)
        self.make_remote_file(dir_name + "/testfile1")
        host.rename(dir_name + "/testfile1", dir_name + "/testfile2")
        assert not host.path.exists(dir_name + "/testfile1")
        assert host.path.exists(dir_name + "/testfile2")


class TestStat(RealFTPTest):

    def test_stat(self):
        host = self.host
        dir_name = "_testdir_"
        file_name = host.path.join(dir_name, "_nonempty_")
        # Make a directory and a file in it.
        self.cleaner.add_dir(dir_name)
        host.mkdir(dir_name)
        with host.open(file_name, "wb") as fobj:
            fobj.write(b"abc\x12\x34def\t")
        # Do some stats
        # - dir
        dir_stat = host.stat(dir_name)
        assert isinstance(dir_stat._st_name, ftputil.compat.unicode_type)
        assert host.listdir(dir_name) == ["_nonempty_"]
        assert host.path.isdir(dir_name)
        assert not host.path.isfile(dir_name)
        assert not host.path.islink(dir_name)
        # - file
        file_stat = host.stat(file_name)
        assert isinstance(file_stat._st_name, ftputil.compat.unicode_type)
        assert not host.path.isdir(file_name)
        assert host.path.isfile(file_name)
        assert not host.path.islink(file_name)
        assert host.path.getsize(file_name) == 9
        # - file's modification time; allow up to two minutes difference
        host.synchronize_times()
        server_mtime = host.path.getmtime(file_name)
        client_mtime = time.mktime(time.localtime())
        calculated_time_shift = server_mtime - client_mtime
        assert not abs(calculated_time_shift-host.time_shift()) > 120

    def test_issomething_for_nonexistent_directory(self):
        host = self.host
        # Check if we get the right results if even the containing
        # directory doesn't exist (see ticket #66).
        nonexistent_path = "/nonexistent/nonexistent"
        assert not host.path.isdir(nonexistent_path)
        assert not host.path.isfile(nonexistent_path)
        assert not host.path.islink(nonexistent_path)

    def test_special_broken_link(self):
        # Test for ticket #39.
        host = self.host
        broken_link_name = os.path.join("dir_with_broken_link", "nonexistent")
        assert (host.lstat(broken_link_name)._st_target ==
                "../nonexistent/nonexistent")
        assert not host.path.isdir(broken_link_name)
        assert not host.path.isfile(broken_link_name)
        assert host.path.islink(broken_link_name)

    def test_concurrent_access(self):
        self.make_remote_file("_testfile_")
        with ftputil.FTPHost(*self.login_data) as host1:
            with ftputil.FTPHost(*self.login_data) as host2:
                stat_result1 = host1.stat("_testfile_")
                stat_result2 = host2.stat("_testfile_")
                assert stat_result1 == stat_result2
                host2.remove("_testfile_")
                # Can still get the result via `host1`
                stat_result1 = host1.stat("_testfile_")
                assert stat_result1 == stat_result2
                # Stat'ing on `host2` gives an exception.
                with pytest.raises(ftputil.error.PermanentError):
                    host2.stat("_testfile_")
                # Stat'ing on `host1` after invalidation
                absolute_path = host1.path.join(host1.getcwd(), "_testfile_")
                host1.stat_cache.invalidate(absolute_path)
                with pytest.raises(ftputil.error.PermanentError):
                    host1.stat("_testfile_")

    def test_cache_auto_resizing(self):
        """Test if the cache is resized appropriately."""
        host = self.host
        cache = host.stat_cache._cache
        # Make sure the cache size isn't adjusted towards smaller values.
        unused_entries = host.listdir("walk_test")
        assert cache.size == ftputil.stat_cache.StatCache._DEFAULT_CACHE_SIZE
        # Make the cache very small initially and see if it gets resized.
        cache.size = 2
        entries = host.listdir("walk_test")
        # The adjusted cache size should be larger or equal to the
        # number of items in `walk_test` and its parent directory. The
        # latter is read implicitly upon `listdir`'s `isdir` call.
        expected_min_cache_size = max(len(host.listdir(host.curdir)),
                                      len(entries))
        assert cache.size >= expected_min_cache_size


class TestUploadAndDownload(RealFTPTest):
    """Test upload and download (including time shift test)."""

    def test_time_shift(self):
        self.host.synchronize_times()
        assert self.host.time_shift() == EXPECTED_TIME_SHIFT

    @pytest.mark.slow_test
    def test_upload(self):
        host = self.host
        host.synchronize_times()
        local_file = "_local_file_"
        remote_file = "_remote_file_"
        # Make local file to upload.
        self.make_local_file()
        # Wait, else small time differences between client and server
        # actually could trigger the update.
        time.sleep(65)
        try:
            self.cleaner.add_file(remote_file)
            host.upload(local_file, remote_file)
            # Retry; shouldn't be uploaded
            uploaded = host.upload_if_newer(local_file, remote_file)
            assert uploaded is False
            # Rewrite the local file.
            self.make_local_file()
            # Retry; should be uploaded now
            uploaded = host.upload_if_newer(local_file, remote_file)
            assert uploaded is True
        finally:
            # Clean up
            os.unlink(local_file)

    @pytest.mark.slow_test
    def test_download(self):
        host = self.host
        host.synchronize_times()
        local_file = "_local_file_"
        remote_file = "_remote_file_"
        # Make a remote file.
        self.make_remote_file(remote_file)
        # File should be downloaded as it's not present yet.
        downloaded = host.download_if_newer(remote_file, local_file)
        assert downloaded is True
        try:
            # If the remote file, taking the datetime precision into
            # account, _might_ be newer, the file will be downloaded
            # again. To prevent this, wait a bit over a minute (the
            # remote precision), then "touch" the local file.
            time.sleep(65)
            # Create empty file.
            with open(local_file, "w") as fobj:
                pass
            # Local file is present and newer, so shouldn't download.
            downloaded = host.download_if_newer(remote_file, local_file)
            assert downloaded is False
            # Re-make the remote file.
            self.make_remote_file(remote_file)
            # Local file is present but possibly older (taking the
            # possible deviation because of the precision into account),
            # so should download.
            downloaded = host.download_if_newer(remote_file, local_file)
            assert downloaded is True
        finally:
            # Clean up.
            os.unlink(local_file)

    def test_callback_with_transfer(self):
        host = self.host
        FILE_NAME = "debian-keyring.tar.gz"
        # Default chunk size as in `FTPHost.copyfileobj`
        MAX_COPY_CHUNK_SIZE = ftputil.file_transfer.MAX_COPY_CHUNK_SIZE
        file_size = host.path.getsize(FILE_NAME)
        chunk_count, _ = divmod(file_size, MAX_COPY_CHUNK_SIZE)
        # Add one chunk for remainder.
        chunk_count += 1
        # Define a callback that just collects all data passed to it.
        transferred_chunks_list = []
        def test_callback(chunk):
            transferred_chunks_list.append(chunk)
        try:
            host.download(FILE_NAME, FILE_NAME, callback=test_callback)
            # Construct a list of data chunks we expect.
            expected_chunks_list = []
            with open(FILE_NAME, "rb") as downloaded_fobj:
                while True:
                    chunk = downloaded_fobj.read(MAX_COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    expected_chunks_list.append(chunk)
            # Examine data collected by callback function.
            assert len(transferred_chunks_list) == chunk_count
            assert transferred_chunks_list == expected_chunks_list
        finally:
            os.unlink(FILE_NAME)


class TestFTPFiles(RealFTPTest):

    def test_only_closed_children(self):
        REMOTE_FILE_NAME = "CONTENTS"
        host = self.host
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj1:
            # Create empty file and close it.
            with host.open(REMOTE_FILE_NAME, "rb") as file_obj2:
                pass
            # This should re-use the second child because the first isn't
            # closed but the second is.
            with host.open(REMOTE_FILE_NAME, "rb") as file_obj:
                assert len(host._children) == 2
                assert file_obj._host is host._children[1]

    def test_no_timed_out_children(self):
        REMOTE_FILE_NAME = "CONTENTS"
        host = self.host
        # Implicitly create child host object.
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj1:
            pass
        # Monkey-patch file to simulate an FTP server timeout below.
        def timed_out_pwd():
            raise ftplib.error_temp("simulated timeout")
        file_obj1._host._session.pwd = timed_out_pwd
        # Try to get a file - which shouldn't be the timed-out file.
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj2:
            assert file_obj1 is not file_obj2
        # Re-use closed and not timed-out child session.
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj3:
            pass
        assert file_obj2 is file_obj3

    def test_no_delayed_226_children(self):
        REMOTE_FILE_NAME = "CONTENTS"
        host = self.host
        # Implicitly create child host object.
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj1:
            pass
        # Monkey-patch file to simulate an FTP server timeout below.
        def timed_out_pwd():
            raise ftplib.error_reply("delayed 226 reply")
        file_obj1._host._session.pwd = timed_out_pwd
        # Try to get a file - which shouldn't be the timed-out file.
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj2:
            assert file_obj1 is not file_obj2
        # Re-use closed and not timed-out child session.
        with host.open(REMOTE_FILE_NAME, "rb") as file_obj3:
            pass
        assert file_obj2 is file_obj3


class TestChmod(RealFTPTest):

    def assert_mode(self, path, expected_mode):
        """
        Return an integer containing the allowed bits in the mode
        change command.

        The `FTPHost` object to test against is `self.host`.
        """
        full_mode = self.host.stat(path).st_mode
        # Remove flags we can't set via `chmod`.
        # Allowed flags according to Python documentation
        # https://docs.python.org/library/stat.html
        allowed_flags = [stat.S_ISUID, stat.S_ISGID, stat.S_ENFMT,
          stat.S_ISVTX, stat.S_IREAD, stat.S_IWRITE, stat.S_IEXEC,
          stat.S_IRWXU, stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR,
          stat.S_IRWXG, stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP,
          stat.S_IRWXO, stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH]
        allowed_mask = functools.reduce(operator.or_, allowed_flags)
        mode = full_mode & allowed_mask
        assert mode == expected_mode, (
                 "mode {0:o} != {1:o}".format(mode, expected_mode))

    def test_chmod_existing_directory(self):
        host = self.host
        host.mkdir("_test dir_")
        self.cleaner.add_dir("_test dir_")
        # Set/get mode of a directory.
        host.chmod("_test dir_", 0o757)
        self.assert_mode("_test dir_", 0o757)
        # Set/get mode in nested directory.
        host.mkdir("_test dir_/nested_dir")
        self.cleaner.add_dir("_test dir_/nested_dir")
        host.chmod("_test dir_/nested_dir", 0o757)
        self.assert_mode("_test dir_/nested_dir", 0o757)

    def test_chmod_existing_file(self):
        host = self.host
        host.mkdir("_test dir_")
        self.cleaner.add_dir("_test dir_")
        # Set/get mode on a file.
        file_name = host.path.join("_test dir_", "_testfile_")
        self.make_remote_file(file_name)
        host.chmod(file_name, 0o646)
        self.assert_mode(file_name, 0o646)

    def test_chmod_nonexistent_path(self):
        # Set/get mode of a non-existing item.
        with pytest.raises(ftputil.error.PermanentError):
            self.host.chmod("nonexistent", 0o757)

    def test_cache_invalidation(self):
        host = self.host
        host.mkdir("_test dir_")
        self.cleaner.add_dir("_test dir_")
        # Make sure the mode is in the cache.
        unused_stat_result = host.stat("_test dir_")
        # Set/get mode of the directory.
        host.chmod("_test dir_", 0o757)
        self.assert_mode("_test dir_", 0o757)
        # Set/get mode on a file.
        file_name = host.path.join("_test dir_", "_testfile_")
        self.make_remote_file(file_name)
        # Make sure the mode is in the cache.
        unused_stat_result = host.stat(file_name)
        host.chmod(file_name, 0o646)
        self.assert_mode(file_name, 0o646)


class TestRestArgument(RealFTPTest):

    TEST_FILE_NAME = "rest_test"

    def setup_method(self, method):
        super(TestRestArgument, self).setup_method(method)
        # Write test file.
        with self.host.open(self.TEST_FILE_NAME, "wb") as fobj:
            fobj.write(b"abcdefghijkl")
        self.cleaner.add_file(self.TEST_FILE_NAME)

    def test_for_reading(self):
        """
        If a `rest` argument is passed to `open`, the following read
        operation should start at the byte given by `rest`.
        """
        with self.host.open(self.TEST_FILE_NAME, "rb", rest=3) as fobj:
            data = fobj.read()
        assert data == b"defghijkl"

    def test_for_writing(self):
        """
        If a `rest` argument is passed to `open`, the following write
        operation should start writing at the byte given by `rest`.
        """
        with self.host.open(self.TEST_FILE_NAME, "wb", rest=3) as fobj:
            fobj.write(b"123")
        with self.host.open(self.TEST_FILE_NAME, "rb") as fobj:
            data = fobj.read()
        assert data == b"abc123"

    def test_invalid_read_from_text_file(self):
        """
        If the `rest` argument is used for reading from a text file,
        a `CommandNotImplementedError` should be raised.
        """
        with pytest.raises(ftputil.error.CommandNotImplementedError):
            self.host.open(self.TEST_FILE_NAME, "r", rest=3)

    def test_invalid_write_to_text_file(self):
        """
        If the `rest` argument is used for reading from a text file,
        a `CommandNotImplementedError` should be raised.
        """
        with pytest.raises(ftputil.error.CommandNotImplementedError):
            self.host.open(self.TEST_FILE_NAME, "w", rest=3)

    # There are no tests for reading and writing beyond the end of a
    # file. For example, if the remote file is 10 bytes long and
    # `open(remote_file, "rb", rest=100)` is used, the server may
    # return an error status code or not.
    #
    # The server I use for testing returns a 554 status when
    # attempting to _read_ beyond the end of the file. On the other
    # hand, if attempting to _write_ beyond the end of the file, the
    # server accepts the request, but starts writing after the end of
    # the file, i. e. appends to the file.
    #
    # Instead of expecting certain responses that may differ between
    # server implementations, I leave the bahavior for too large
    # `rest` arguments undefined. In practice, this shouldn't be a
    # problem because the `rest` argument should only be used for
    # error recovery, and in this case a valid byte count for the
    # `rest` argument should be known.


class TestOther(RealFTPTest):

    def test_open_for_reading(self):
        # Test for issues #17 and #51,
        # http://ftputil.sschwarzer.net/trac/ticket/17 and
        # http://ftputil.sschwarzer.net/trac/ticket/51 .
        file1 = self.host.open("debian-keyring.tar.gz", "rb")
        time.sleep(1)
        # Depending on the FTP server, this might return a status code
        # unexpected by `ftplib` or block the socket connection until
        # a server-side timeout.
        file1.close()

    def test_subsequent_reading(self):
        # Open a file for reading.
        with self.host.open("CONTENTS", "rb") as file1:
            pass
        # Make sure that there are no problems if the connection is reused.
        with self.host.open("CONTENTS", "rb") as file2:
            pass
        assert file1._session is file2._session

    def test_names_with_spaces(self):
        # Test if directories and files with spaces in their names
        # can be used.
        host = self.host
        assert host.path.isdir("dir with spaces")
        assert (host.listdir("dir with spaces") ==
                ["second dir", "some file", "some_file"])
        assert host.path.isdir("dir with spaces/second dir")
        assert host.path.isfile("dir with spaces/some_file")
        assert host.path.isfile("dir with spaces/some file")

    def test_synchronize_times_without_write_access(self):
        """Test failing synchronization because of non-writable directory."""
        host = self.host
        # This isn't writable by the ftp account the tests are run under.
        host.chdir("rootdir1")
        with pytest.raises(ftputil.error.TimeShiftError):
            host.synchronize_times()

    def test_listdir_with_non_ascii_byte_string(self):
        """
        `listdir` should accept byte strings with non-ASCII
        characters and return non-ASCII characters in directory or
        file names.
        """
        host = self.host
        path = "äbc".encode("UTF-8")
        names = host.listdir(path)
        assert names[0] == b"file1"
        assert names[1] == "file1_ö".encode("UTF-8")

    def test_listdir_with_non_ascii_unicode_string(self):
        """
        `listdir` should accept unicode strings with non-ASCII
        characters and return non-ASCII characters in directory or
        file names.
        """
        host = self.host
        # `ftplib` under Python 3 only works correctly if the unicode
        # strings are decoded from latin1. Under Python 2, ftputil
        # is supposed to provide a compatible interface.
        path = "äbc".encode("UTF-8").decode("latin1")
        names = host.listdir(path)
        assert names[0] == "file1"
        assert names[1] == "file1_ö".encode("UTF-8").decode("latin1")

    def test_path_with_non_latin1_unicode_string(self):
        """
        ftputil operations shouldn't accept file paths with non-latin1
        characters.
        """
        # Use some musical symbols. These are certainly not latin1.
        path = "𝄞𝄢"
        # `UnicodeEncodeError` is also the exception that `ftplib`
        # raises if it gets a non-latin1 path.
        with pytest.raises(UnicodeEncodeError):
            self.host.mkdir(path)

    def test_list_a_option(self):
        # For this test to pass, the server must _not_ list "hidden"
        # files by default but instead only when the `LIST` `-a`
        # option is used.
        host = self.host
        assert host.use_list_a_option
        directory_entries = host.listdir(host.curdir)
        assert ".hidden" in directory_entries
        host.use_list_a_option = False
        directory_entries = host.listdir(host.curdir)
        assert ".hidden" not in directory_entries

    def _make_objects_to_be_garbage_collected(self):
        for _ in range(10):
            with ftputil.FTPHost(*self.login_data) as host:
                for _ in range(10):
                    unused_stat_result = host.stat("CONTENTS")
                    with host.open("CONTENTS") as fobj:
                        unused_data = fobj.read()

    def test_garbage_collection(self):
        """Test whether there are cycles which prevent garbage collection."""
        gc.collect()
        objects_before_test = len(gc.garbage)
        self._make_objects_to_be_garbage_collected()
        gc.collect()
        objects_after_test = len(gc.garbage)
        assert not objects_after_test - objects_before_test

    @pytest.mark.skipif(
      ftputil.compat.python_version > 2,
      reason="test requires M2Crypto which only works on Python 2")
    def test_m2crypto_session(self):
        """
        Test if a session with `M2Crypto.ftpslib.FTP_TLS` is set up
        correctly and works with unicode input.
        """
        # See ticket #78.
        #
        # M2Crypto is only available for Python 2.
        import M2Crypto
        factory = ftputil.session.session_factory(
                    base_class=M2Crypto.ftpslib.FTP_TLS,
                    encrypt_data_channel=True)
        with ftputil.FTPHost(*self.login_data, session_factory=factory) as host:
            # Test if unicode argument works.
            files = host.listdir(".")
        assert "CONTENTS" in files
