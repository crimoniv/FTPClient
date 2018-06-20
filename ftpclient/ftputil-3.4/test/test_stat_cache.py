# Copyright (C) 2006-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

from __future__ import unicode_literals

import time

import pytest

import ftputil.error
import ftputil.stat_cache

from test import test_base


class TestStatCache(object):

    def setup_method(self, method):
        self.cache = ftputil.stat_cache.StatCache()

    def test_get_set(self):
        with pytest.raises(ftputil.error.CacheMissError):
            self.cache.__getitem__("/path")
        self.cache["/path"] = "test"
        assert self.cache["/path"] == "test"

    def test_invalidate(self):
        # Don't raise a `CacheMissError` for missing paths
        self.cache.invalidate("/path")
        self.cache["/path"] = "test"
        self.cache.invalidate("/path")
        assert len(self.cache) == 0

    def test_clear(self):
        self.cache["/path1"] = "test1"
        self.cache["/path2"] = "test2"
        self.cache.clear()
        assert len(self.cache) == 0

    def test_contains(self):
        self.cache["/path1"] = "test1"
        assert "/path1" in self.cache
        assert "/path2" not in self.cache

    def test_len(self):
        assert len(self.cache) == 0
        self.cache["/path1"] = "test1"
        self.cache["/path2"] = "test2"
        assert len(self.cache) == 2

    def test_resize(self):
        self.cache.resize(100)
        # Don't grow the cache beyond it's set size.
        for i in range(150):
            self.cache["/{0:d}".format(i)] = i
        assert len(self.cache) == 100

    def test_max_age1(self):
        """Set expiration after setting a cache item."""
        self.cache["/path1"] = "test1"
        # Expire after one second
        self.cache.max_age = 1
        time.sleep(0.5)
        # Should still be present
        assert self.cache["/path1"] == "test1"
        time.sleep(0.6)
        # Should have expired (_setting_ the cache counts)
        with pytest.raises(ftputil.error.CacheMissError):
            self.cache.__getitem__("/path1")

    def test_max_age2(self):
        """Set expiration before setting a cache item."""
        # Expire after one second
        self.cache.max_age = 1
        self.cache["/path1"] = "test1"
        time.sleep(0.5)
        # Should still be present
        assert self.cache["/path1"] == "test1"
        time.sleep(0.6)
        # Should have expired (_setting_ the cache counts)
        with pytest.raises(ftputil.error.CacheMissError):
            self.cache.__getitem__("/path1")

    def test_disabled(self):
        self.cache["/path1"] = "test1"
        self.cache.disable()
        self.cache["/path2"] = "test2"
        with pytest.raises(ftputil.error.CacheMissError):
            self.cache.__getitem__("/path1")
        with pytest.raises(ftputil.error.CacheMissError):
            self.cache.__getitem__("/path2")
        assert len(self.cache) == 1
        # Don't raise a `CacheMissError` for missing paths.
        self.cache.invalidate("/path2")

    def test_cache_size_zero(self):
        host = test_base.ftp_host_factory()
        with pytest.raises(ValueError):
            host.stat_cache.resize(0)
        # If bug #38 was present, this raised an `IndexError`.
        items = host.listdir(host.curdir)
        assert items[:3] == ["chemeng", "download", "image"]
