# Copyright (C) 2003-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

import stat
import time

import pytest

import ftputil
import ftputil.compat
import ftputil.error
import ftputil.stat
from ftputil.stat import MINUTE_PRECISION, DAY_PRECISION, UNKNOWN_PRECISION

from test import test_base
from test import mock_ftplib


def _test_stat(session_factory):
    host = test_base.ftp_host_factory(session_factory=session_factory)
    stat = ftputil.stat._Stat(host)
    # Use Unix format parser explicitly. This doesn't exclude switching
    # to the MS format parser later if the test allows this switching.
    stat._parser = ftputil.stat.UnixParser()
    return stat


# Special value to handle special case of datetimes before the epoch.
EPOCH = time.gmtime(0)[:6]

def stat_tuple_to_seconds(t):
    """
    Return a float number representing the local time associated with
    the six-element tuple `t`.
    """
    assert len(t) == 6, \
             "need a six-element tuple (year, month, day, hour, min, sec)"
    # Do _not_ apply `time.mktime` to the `EPOCH` value below. On some
    # platforms (e. g. Windows) this might cause an `OverflowError`.
    if t == EPOCH:
        return 0.0
    else:
        return time.mktime(t + (0, 0, -1))


class TestParsers(object):

    #
    # Helper methods
    #
    def _test_valid_lines(self, parser_class, lines, expected_stat_results):
        parser = parser_class()
        for line, expected_stat_result in zip(lines, expected_stat_results):
            # Convert to list to compare with the list `expected_stat_results`.
            parse_result = parser.parse_line(line)
            stat_result = list(parse_result) + \
                          [parse_result._st_mtime_precision,
                           parse_result._st_name,
                           parse_result._st_target]
            # Convert time tuple to seconds.
            expected_stat_result[8] = \
              stat_tuple_to_seconds(expected_stat_result[8])
            # Compare lists.
            assert stat_result == expected_stat_result

    def _test_invalid_lines(self, parser_class, lines):
        parser = parser_class()
        for line in lines:
            with pytest.raises(ftputil.error.ParserError):
                parser.parse_line(line)

    def _expected_year(self):
        """
        Return the expected year for the second line in the
        listing in `test_valid_unix_lines`.
        """
        # If in this year it's after Dec 19, 23:11, use the current
        # year, else use the previous year. This datetime value
        # corresponds to the hard-coded value in the string lists
        # below.
        now = time.localtime()
        # We need only month, day, hour and minute.
        current_time_parts = now[1:5]
        time_parts_in_listing = (12, 19, 23, 11)
        if current_time_parts > time_parts_in_listing:
            return now[0]
        else:
            return now[0] - 1

    #
    # Unix parser
    #
    def test_valid_unix_lines(self):
        lines = [
          "drwxr-sr-x   2 45854    200           512 May  4  2000 "
            "chemeng link -> chemeng target",
          # The year value for this line will change with the actual time.
          "-rw-r--r--   1 45854    200          4604 Dec 19 23:11 index.html",
          "drwxr-sr-x   2 45854    200           512 May 29  2000 os2",
          "----------   2 45854    200           512 May 29  2000 some_file",
          "lrwxrwxrwx   2 45854    200           512 May 29  2000 osup -> "
                                                                  "../os2"
        ]
        expected_stat_results = [
          [17901, None, None, 2, "45854", "200", 512, None,
           (2000, 5, 4, 0, 0, 0), None, DAY_PRECISION,
           "chemeng link", "chemeng target"],
          [33188, None, None, 1, "45854", "200", 4604, None,
           (self._expected_year(), 12, 19, 23, 11, 0), None, MINUTE_PRECISION,
           "index.html", None],
          [17901, None, None, 2, "45854", "200", 512, None,
           (2000, 5, 29, 0, 0, 0), None, DAY_PRECISION,
           "os2", None],
          [32768, None, None, 2, "45854", "200", 512, None,
           (2000, 5, 29, 0, 0, 0), None, DAY_PRECISION,
           "some_file", None],
          [41471, None, None, 2, "45854", "200", 512, None,
           (2000, 5, 29, 0, 0, 0), None, DAY_PRECISION,
           "osup", "../os2"]
        ]
        self._test_valid_lines(ftputil.stat.UnixParser, lines,
                               expected_stat_results)

    def test_alternative_unix_format(self):
        # See http://ftputil.sschwarzer.net/trac/ticket/12 for a
        # description for the need for an alternative format.
        lines = [
          "drwxr-sr-x   2   200           512 May  4  2000 "
            "chemeng link -> chemeng target",
          # The year value for this line will change with the actual time.
          "-rw-r--r--   1   200          4604 Dec 19 23:11 index.html",
          "drwxr-sr-x   2   200           512 May 29  2000 os2",
          "lrwxrwxrwx   2   200           512 May 29  2000 osup -> ../os2"
        ]
        expected_stat_results = [
          [17901, None, None, 2, None, "200", 512, None,
           (2000, 5, 4, 0, 0, 0), None, DAY_PRECISION,
           "chemeng link", "chemeng target"],
          [33188, None, None, 1, None, "200", 4604, None,
           (self._expected_year(), 12, 19, 23, 11, 0), None, MINUTE_PRECISION,
           "index.html", None],
          [17901, None, None, 2, None, "200", 512, None,
           (2000, 5, 29, 0, 0, 0), None, DAY_PRECISION,
           "os2", None],
          [41471, None, None, 2, None, "200", 512, None,
           (2000, 5, 29, 0, 0, 0), None, DAY_PRECISION,
           "osup", "../os2"]
        ]
        self._test_valid_lines(ftputil.stat.UnixParser, lines,
                               expected_stat_results)

    def test_pre_epoch_times_for_unix(self):
        # See http://ftputil.sschwarzer.net/trac/ticket/83 .
        # `mirrors.ibiblio.org` returns dates before the "epoch" that
        # cause an `OverflowError` in `mktime` on some platforms,
        # e. g. Windows.
        lines = [
          "-rw-r--r--   1 45854    200          4604 May  4  1968 index.html",
          "-rw-r--r--   1 45854    200          4604 Dec 31  1969 index.html",
          "-rw-r--r--   1 45854    200          4604 May  4  1800 index.html",
        ]
        expected_stat_result = \
          [33188, None, None, 1, "45854", "200", 4604, None,
           EPOCH, None, UNKNOWN_PRECISION, "index.html", None]
        # Make shallow copies to avoid converting the time tuple more
        # than once in _test_valid_lines`.
        expected_stat_results = [expected_stat_result[:],
                                 expected_stat_result[:],
                                 expected_stat_result[:]]
        self._test_valid_lines(ftputil.stat.UnixParser, lines,
                               expected_stat_results)

    def test_invalid_unix_lines(self):
        lines = [
          # Not intended to be parsed. Should have been filtered out by
          # `ignores_line`.
          "total 14",
          # Invalid month abbreviation
          "drwxr-sr-x   2 45854    200           512 Max  4  2000 chemeng",
          # Year value isn't an integer
          "drwxr-sr-x   2 45854    200           512 May  4  abcd chemeng",
          # Day value isn't an integer
          "drwxr-sr-x   2 45854    200           512 May ab  2000 chemeng",
          # Hour value isn't an integer
          "-rw-r--r--   1 45854    200          4604 Dec 19 ab:11 index.html",
          # Minute value isn't an integer
          "-rw-r--r--   1 45854    200          4604 Dec 19 23:ab index.html",
          # Day value too large
          "drwxr-sr-x   2 45854    200           512 May 32  2000 chemeng",
          # Incomplete mode
          "drwxr-sr-    2 45854    200           512 May  4  2000 chemeng",
          # Invalid first letter in mode
          "xrwxr-sr-x   2 45854    200           512 May  4  2000 chemeng",
          # Ditto, plus invalid size value
          "xrwxr-sr-x   2 45854    200           51x May  4  2000 chemeng",
          # Is this `os1 -> os2` pointing to `os3`, or `os1` pointing
          # to `os2 -> os3` or the plain name `os1 -> os2 -> os3`? We
          # don't know, so we consider the line invalid.
          "drwxr-sr-x   2 45854    200           512 May 29  2000 "
            "os1 -> os2 -> os3",
          # Missing name
          "-rwxr-sr-x   2 45854    200           51x May  4  2000 ",
        ]
        self._test_invalid_lines(ftputil.stat.UnixParser, lines)

    #
    # Microsoft parser
    #
    def test_valid_ms_lines_two_digit_year(self):
        lines = [
          "07-27-01  11:16AM       <DIR>          Test",
          "10-23-95  03:25PM       <DIR>          WindowsXP",
          "07-17-00  02:08PM             12266720 test.exe",
          "07-17-09  12:08AM             12266720 test.exe",
          "07-17-09  12:08PM             12266720 test.exe"
        ]
        expected_stat_results = [
          [16640, None, None, None, None, None, None, None,
           (2001, 7, 27, 11, 16, 0), None, MINUTE_PRECISION,
           "Test", None],
          [16640, None, None, None, None, None, None, None,
           (1995, 10, 23, 15, 25, 0), None, MINUTE_PRECISION,
           "WindowsXP", None],
          [33024, None, None, None, None, None, 12266720, None,
           (2000, 7, 17, 14, 8, 0), None, MINUTE_PRECISION,
           "test.exe", None],
          [33024, None, None, None, None, None, 12266720, None,
           (2009, 7, 17, 0, 8, 0), None, MINUTE_PRECISION,
           "test.exe", None],
          [33024, None, None, None, None, None, 12266720, None,
           (2009, 7, 17, 12, 8, 0), None, MINUTE_PRECISION,
           "test.exe", None]
        ]
        self._test_valid_lines(ftputil.stat.MSParser, lines,
                               expected_stat_results)

    def test_valid_ms_lines_four_digit_year(self):
        # See http://ftputil.sschwarzer.net/trac/ticket/67
        lines = [
          "10-19-2012  03:13PM       <DIR>          SYNCDEST",
          "10-19-2012  03:13PM       <DIR>          SYNCSOURCE",
          "10-19-1968  03:13PM       <DIR>          SYNC"
        ]
        expected_stat_results = [
          [16640, None, None, None, None, None, None, None,
           (2012, 10, 19, 15, 13, 0), None, MINUTE_PRECISION,
           "SYNCDEST", None],
          [16640, None, None, None, None, None, None, None,
           (2012, 10, 19, 15, 13, 0), None, MINUTE_PRECISION,
           "SYNCSOURCE", None],
          [16640, None, None, None, None, None, None, None,
           EPOCH, None, UNKNOWN_PRECISION,
           "SYNC", None],
        ]
        self._test_valid_lines(ftputil.stat.MSParser, lines,
                               expected_stat_results)

    def test_invalid_ms_lines(self):
        lines = [
          # Neither "<DIR>" nor a size present
          "07-27-01  11:16AM                      Test",
          # "AM"/"PM" missing
          "07-17-00  02:08             12266720 test.exe",
          # Year not an int
          "07-17-ab  02:08AM           12266720 test.exe",
          # Month not an int
          "ab-17-00  02:08AM           12266720 test.exe",
          # Day not an int
          "07-ab-00  02:08AM           12266720 test.exe",
          # Hour not an int
          "07-17-00  ab:08AM           12266720 test.exe",
          # Invalid size value
          "07-17-00  02:08AM           1226672x test.exe"
        ]
        self._test_invalid_lines(ftputil.stat.MSParser, lines)

    #
    # The following code checks if the decision logic in the Unix
    # line parser for determining the year works.
    #
    def datetime_string(self, time_float):
        """
        Return a datetime string generated from the value in
        `time_float`. The parameter value is a floating point value
        as returned by `time.time()`. The returned string is built as
        if it were from a Unix FTP server (format: MMM dd hh:mm")
        """
        time_tuple = time.localtime(time_float)
        return time.strftime("%b %d %H:%M", time_tuple)

    def dir_line(self, time_float):
        """
        Return a directory line as from a Unix FTP server. Most of
        the contents are fixed, but the timestamp is made from
        `time_float` (seconds since the epoch, as from `time.time()`).
        """
        line_template = \
          "-rw-r--r--   1   45854   200   4604   {0}   index.html"
        return line_template.format(self.datetime_string(time_float))

    def assert_equal_times(self, time1, time2):
        """
        Check if both times (seconds since the epoch) are equal. For
        the purpose of this test, two times are "equal" if they
        differ no more than one minute from each other.
        """
        abs_difference = abs(time1 - time2)
        assert abs_difference <= 60.0, \
                 "Difference is %s seconds" % abs_difference

    def _test_time_shift(self, supposed_time_shift, deviation=0.0):
        """
        Check if the stat parser considers the time shift value
        correctly. `deviation` is the difference between the actual
        time shift and the supposed time shift, which is rounded
        to full hours.
        """
        host = test_base.ftp_host_factory()
        # Explicitly use Unix format parser here.
        host._stat._parser = ftputil.stat.UnixParser()
        host.set_time_shift(supposed_time_shift)
        server_time = time.time() + supposed_time_shift + deviation
        stat_result = host._stat._parser.parse_line(self.dir_line(server_time),
                                                    host.time_shift())
        self.assert_equal_times(stat_result.st_mtime, server_time)

    def test_time_shifts(self):
        """Test correct year depending on time shift value."""
        # 1. test: Client and server share the same local time
        self._test_time_shift(0.0)
        # 2. test: Server is three hours ahead of client
        self._test_time_shift(3 * 60 * 60)
        # 3. test: Client is three hours ahead of server
        self._test_time_shift(- 3 * 60 * 60)
        # 4. test: Server is supposed to be three hours ahead, but
        #    is ahead three hours and one minute
        self._test_time_shift(3 * 60 * 60, 60)
        # 5. test: Server is supposed to be three hours ahead, but
        #    is ahead three hours minus one minute
        self._test_time_shift(3 * 60 * 60, -60)
        # 6. test: Client is supposed to be three hours ahead, but
        #    is ahead three hours and one minute
        self._test_time_shift(-3 * 60 * 60, -60)
        # 7. test: Client is supposed to be three hours ahead, but
        #    is ahead three hours minus one minute
        self._test_time_shift(-3 * 60 * 60, 60)


class TestLstatAndStat(object):
    """
    Test `FTPHost.lstat` and `FTPHost.stat` (test currently only
    implemented for Unix server format).
    """

    def setup_method(self, method):
        # Most tests in this class need the mock session class with
        # Unix format, so make this the default. Tests which need
        # the MS format can overwrite `self.stat` later.
        self.stat = \
          _test_stat(session_factory=mock_ftplib.MockUnixFormatSession)

    def test_repr(self):
        """Test if the `repr` result looks like a named tuple."""
        stat_result = self.stat._lstat("/home/sschwarzer/chemeng")
        # Only under Python 2, unicode strings have the `u` prefix.
        # TODO: Make the value for `st_mtime` robust against DST "time
        # zone" changes.
        if ftputil.compat.python_version == 2:
            expected_result = (
              b"StatResult(st_mode=17901, st_ino=None, st_dev=None, "
              b"st_nlink=2, st_uid=u'45854', st_gid=u'200', st_size=512, "
              b"st_atime=None, st_mtime=957391200.0, st_ctime=None)")
        else:
            expected_result = (
              "StatResult(st_mode=17901, st_ino=None, st_dev=None, "
              "st_nlink=2, st_uid='45854', st_gid='200', st_size=512, "
              "st_atime=None, st_mtime=957391200.0, st_ctime=None)")
        assert repr(stat_result) == expected_result

    def test_failing_lstat(self):
        """Test whether `lstat` fails for a nonexistent path."""
        with pytest.raises(ftputil.error.PermanentError):
            self.stat._lstat("/home/sschw/notthere")
        with pytest.raises(ftputil.error.PermanentError):
            self.stat._lstat("/home/sschwarzer/notthere")

    def test_lstat_for_root(self):
        """
        Test `lstat` for `/` .

        Note: `(l)stat` works by going one directory up and parsing
        the output of an FTP `LIST` command. Unfortunately, it's not
        possible to do this for the root directory `/`.
        """
        with pytest.raises(ftputil.error.RootDirError) as exc_info:
            self.stat._lstat("/")
        # `RootDirError` is "outside" the `FTPOSError` hierarchy.
        assert not isinstance(exc_info.value, ftputil.error.FTPOSError)
        del exc_info

    def test_lstat_one_unix_file(self):
        """Test `lstat` for a file described in Unix-style format."""
        stat_result = self.stat._lstat("/home/sschwarzer/index.html")
        # Second form is needed for Python 3
        assert oct(stat_result.st_mode) in ("0100644", "0o100644")
        assert stat_result.st_size == 4604
        assert stat_result._st_mtime_precision == 60

    def test_lstat_one_ms_file(self):
        """Test `lstat` for a file described in DOS-style format."""
        self.stat = _test_stat(session_factory=mock_ftplib.MockMSFormatSession)
        stat_result = self.stat._lstat("/home/msformat/abcd.exe")
        assert stat_result._st_mtime_precision == 60

    def test_lstat_one_unix_dir(self):
        """Test `lstat` for a directory described in Unix-style format."""
        stat_result = self.stat._lstat("/home/sschwarzer/scios2")
        # Second form is needed for Python 3
        assert oct(stat_result.st_mode) in ("042755", "0o42755")
        assert stat_result.st_ino is None
        assert stat_result.st_dev is None
        assert stat_result.st_nlink == 6
        assert stat_result.st_uid == "45854"
        assert stat_result.st_gid == "200"
        assert stat_result.st_size == 512
        assert stat_result.st_atime is None
        assert (stat_result.st_mtime ==
                stat_tuple_to_seconds((1999, 9, 20, 0, 0, 0)))
        assert stat_result.st_ctime is None
        assert stat_result._st_mtime_precision == 24*60*60
        assert stat_result == (17901, None, None, 6, "45854", "200", 512, None,
                               stat_tuple_to_seconds((1999, 9, 20, 0, 0, 0)),
                               None)

    def test_lstat_one_ms_dir(self):
        """Test `lstat` for a directory described in DOS-style format."""
        self.stat = _test_stat(session_factory=mock_ftplib.MockMSFormatSession)
        stat_result = self.stat._lstat("/home/msformat/WindowsXP")
        assert stat_result._st_mtime_precision == 60

    def test_lstat_via_stat_module(self):
        """Test `lstat` indirectly via `stat` module."""
        stat_result = self.stat._lstat("/home/sschwarzer/")
        assert stat.S_ISDIR(stat_result.st_mode)

    def test_stat_following_link(self):
        """Test `stat` when invoked on a link."""
        # Simple link
        stat_result = self.stat._stat("/home/link")
        assert stat_result.st_size == 4604
        # Link pointing to a link
        stat_result = self.stat._stat("/home/python/link_link")
        assert stat_result.st_size == 4604
        stat_result = self.stat._stat("../python/link_link")
        assert stat_result.st_size == 4604
        # Recursive link structures
        with pytest.raises(ftputil.error.PermanentError):
            self.stat._stat("../python/bad_link")
        with pytest.raises(ftputil.error.PermanentError):
            self.stat._stat("/home/bad_link")

    #
    # Test automatic switching of Unix/MS parsers
    #
    def test_parser_switching_with_permanent_error(self):
        """Test non-switching of parser format with `PermanentError`."""
        self.stat = _test_stat(session_factory=mock_ftplib.MockMSFormatSession)
        assert self.stat._allow_parser_switching is True
        # With these directory contents, we get a `ParserError` for
        # the Unix parser first, so `_allow_parser_switching` can be
        # switched off no matter whether we got a `PermanentError`
        # afterward or not.
        with pytest.raises(ftputil.error.PermanentError):
            self.stat._lstat("/home/msformat/nonexistent")
        assert self.stat._allow_parser_switching is False

    def test_parser_switching_default_to_unix(self):
        """Test non-switching of parser format; stay with Unix."""
        assert self.stat._allow_parser_switching is True
        assert isinstance(self.stat._parser, ftputil.stat.UnixParser)
        stat_result = self.stat._lstat("/home/sschwarzer/index.html")
        # The Unix parser worked, so keep it.
        assert isinstance(self.stat._parser, ftputil.stat.UnixParser)
        assert self.stat._allow_parser_switching is False

    def test_parser_switching_to_ms(self):
        """Test switching of parser from Unix to MS format."""
        self.stat = _test_stat(session_factory=mock_ftplib.MockMSFormatSession)
        assert self.stat._allow_parser_switching is True
        assert isinstance(self.stat._parser, ftputil.stat.UnixParser)
        # Parsing the directory `/home/msformat` with the Unix parser
        # fails, so switch to the MS parser.
        stat_result = self.stat._lstat("/home/msformat/abcd.exe")
        assert isinstance(self.stat._parser, ftputil.stat.MSParser)
        assert self.stat._allow_parser_switching is False
        assert stat_result._st_name == "abcd.exe"
        assert stat_result.st_size == 12266720

    def test_parser_switching_regarding_empty_dir(self):
        """Test switching of parser if a directory is empty."""
        self.stat = _test_stat(session_factory=mock_ftplib.MockMSFormatSession)
        assert self.stat._allow_parser_switching is True
        # When the directory we're looking into doesn't give us any
        # lines we can't decide whether the first parser worked,
        # because it wasn't applied. So keep the parser for now.
        result = self.stat._listdir("/home/msformat/XPLaunch/empty")
        assert result == []
        assert self.stat._allow_parser_switching is True
        assert isinstance(self.stat._parser, ftputil.stat.UnixParser)


class TestListdir(object):
    """Test `FTPHost.listdir`."""

    def setup_method(self, method):
        self.stat = \
          _test_stat(session_factory=mock_ftplib.MockUnixFormatSession)

    def test_failing_listdir(self):
        """Test failing `FTPHost.listdir`."""
        with pytest.raises(ftputil.error.PermanentError):
            self.stat._listdir("notthere")

    def test_succeeding_listdir(self):
        """Test succeeding `FTPHost.listdir`."""
        # Do we have all expected "files"?
        assert len(self.stat._listdir(".")) == 9
        # Have they the expected names?
        expected = ("chemeng download image index.html os2 "
                    "osup publications python scios2").split()
        remote_file_list = self.stat._listdir(".")
        for file in expected:
            assert file in remote_file_list
