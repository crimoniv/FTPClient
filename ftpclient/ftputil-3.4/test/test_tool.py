# Copyright (C) 2013-2016, Stefan Schwarzer
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

from __future__ import unicode_literals

import ftputil.compat as compat
import ftputil.tool


class TestSameStringTypeAs(object):

    # The first check for equality is enough for Python 3, where
    # comparing a byte string and unicode string would raise an
    # exception. However, we need the second test for Python 2.

    def test_to_bytes(self):
        result = ftputil.tool.same_string_type_as(b"abc", "def")
        assert result == b"def"
        assert isinstance(result, compat.bytes_type)

    def test_to_unicode(self):
        result = ftputil.tool.same_string_type_as("abc", b"def")
        assert result == "def"
        assert isinstance(result, compat.unicode_type)

    def test_both_bytes_type(self):
        result = ftputil.tool.same_string_type_as(b"abc", b"def")
        assert result == b"def"
        assert isinstance(result, compat.bytes_type)

    def test_both_unicode_type(self):
        result = ftputil.tool.same_string_type_as("abc", "def")
        assert result == "def"
        assert isinstance(result, compat.unicode_type)


class TestSimpleConversions(object):

    def test_as_bytes(self):
        result = ftputil.tool.as_bytes(b"abc")
        assert result == b"abc"
        assert isinstance(result, compat.bytes_type)
        result = ftputil.tool.as_bytes("abc")
        assert result == b"abc"
        assert isinstance(result, compat.bytes_type)
        
    def test_as_unicode(self):
        result = ftputil.tool.as_unicode(b"abc")
        assert result == "abc"
        assert isinstance(result, compat.unicode_type)
        result = ftputil.tool.as_unicode("abc")
        assert result == "abc"
        assert isinstance(result, compat.unicode_type)


class TestEncodeIfUnicode(object):

    def test_do_encode(self):
        string = "abc"
        converted_string = ftputil.tool.encode_if_unicode(string, "latin1")
        assert isinstance(converted_string, compat.bytes_type)

    def test_dont_encode(self):
        string = b"abc"
        not_converted_string = ftputil.tool.encode_if_unicode(string, "latin1")
        assert string == not_converted_string
        assert isinstance(not_converted_string, compat.bytes_type)
