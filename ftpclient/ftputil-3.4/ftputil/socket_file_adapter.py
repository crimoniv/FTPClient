# Copyright (C) 2014, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

"""
See docstring of class `BufferedIO`.
"""

import io


__all__ = ["BufferedIOAdapter"]


class BufferedIOAdapter(io.BufferedIOBase):
    """
    Adapt a file object returned from `socket.makefile` to the
    interfaces of `io.BufferedReader` or `io.BufferedWriter`, so that
    the new object can be wrapped by `io.TextIOWrapper`.

    This is only needed with Python 2, since in Python 3
    `socket.makefile` already returns a `BufferedReader` or
    `BufferedWriter` object (depending on mode).
    """

    def __init__(self, fobj, is_readable=False, is_writable=False):
        # Don't call baseclass constructor for this adapter.
        # pylint: disable=super-init-not-called
        #
        # This is the return value of `socket.makefile` and is already
        # buffered.
        self.raw = fobj
        self._is_readable = is_readable
        self._is_writable = is_writable

    @property
    def closed(self):
        # pylint: disable=missing-docstring
        return self.raw.closed

    def close(self):
        self.raw.close()

    def fileno(self):
        return self.raw.fileno()

    def isatty(self):
        # It's highly unlikely that this file is interactive.
        return False

    def seekable(self):
        return False

    #
    # Interface for `BufferedReader`
    #
    def readable(self):
        return self._is_readable

    def read(self, *arg):
        return self.raw.read(*arg)

    read1 = read

    def readline(self, *arg):
        return self.raw.readline(*arg)

    def readlines(self, *arg):
        return self.raw.readlines(*arg)

    def readinto(self, bytearray_):
        data = self.raw.read(len(bytearray_))
        bytearray_[:len(data)] = data
        return len(data)

    #
    # Interface for `BufferedWriter`
    #
    def writable(self):
        return self._is_writable

    def flush(self):
        self.raw.flush()

    # Derived from `socket.py` in Python 2.6 and 2.7.
    # There doesn't seem to be a public API for this.
    def _write_buffer_size(self):
        """Return current size of the write buffer in bytes."""
        # pylint: disable=protected-access
        if hasattr(self.raw, "_wbuf_len"):
            # Python 2.6.3 - 2.7.5
            return self.raw._wbuf_len
        elif hasattr(self.raw, "_get_wbuf_len"):
            # Python 2.6 - 2.6.2. (Strictly speaking, all other
            # Python 2.6 versions have a `_get_wbuf_len` method, but
            # for 2.6.3 and up it returns `_wbuf_len`).
            return self.raw._get_wbuf_len()
        else:
            # Fallback. In the context of `write` this means the file
            # appears to be unbuffered.
            return 0

    def write(self, bytes_or_bytearray):
        # `BufferedWriter.write` has to return the number of written
        # bytes, but files returned from `socket.makefile` in Python 2
        # return `None`. Hence provide a workaround.
        old_buffer_byte_count = self._write_buffer_size()
        added_byte_count = len(bytes_or_bytearray)
        self.raw.write(bytes_or_bytearray)
        new_buffer_byte_count = self._write_buffer_size()
        return (old_buffer_byte_count + added_byte_count -
                new_buffer_byte_count)

    def writelines(self, lines):
        self.raw.writelines(lines)
