import errno
import re
import stat
from datetime import datetime
from io import UnsupportedOperation
from os.path import commonprefix, join as pathjoin

from tempfile import NamedTemporaryFile

from fman import fs, show_status_message
from fman.fs import FileSystem, cached
from fman.url import join as urljoin, splitscheme

from .ftp import FtpWrapper

is_ftp = re.compile('^ftps?://').match
is_file = re.compile('^file://').match


class FtpFs(FileSystem):
    scheme = 'ftp://'

    def get_default_columns(self, path):
        return (
            'core.Name', 'core.Size', 'core.Modified',
            'ftpclient.columns.Permissions', 'ftpclient.columns.Owner',
            'ftpclient.columns.Group')

    @cached
    def size_bytes(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.path.getsize(ftp.path)

    @cached
    def modified_datetime(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return datetime.utcfromtimestamp(ftp.conn.path.getmtime(ftp.path))

    @cached
    def get_permissions(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return stat.filemode(ftp.conn.lstat(ftp.path).st_mode)

    @cached
    def get_owner(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.lstat(ftp.path).st_uid

    @cached
    def get_group(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.lstat(ftp.path).st_gid

    @cached
    def exists(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.path.exists(ftp.path)

    @cached
    def is_dir(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.path.isdir(ftp.path)

    def iterdir(self, path):
        show_status_message('Loading %s...' % (path,))
        with FtpWrapper(self.scheme + path) as ftp:
            for name in ftp.conn.listdir(ftp.path):
                self.get_stats(pathjoin(path, name))
                yield name
        show_status_message('Ready.', timeout_secs=0)

    def delete(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            if self.is_dir(path):
                ftp.conn.rmtree(ftp.path)
            else:
                ftp.conn.remove(ftp.path)

    def move_to_trash(self, path):
        # ENOSYS: Function not implemented
        raise OSError(errno.ENOSYS, "FTP has no Trash support")

    def mkdir(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            ftp.conn.makedirs(ftp.path)

    def touch(self, path):
        if self.exists(path):
            raise OSError(errno.EEXIST, "File exists")
        with FtpWrapper(self.scheme + path) as ftp:
            with NamedTemporaryFile(delete=True) as tmp:
                ftp.conn.upload(tmp.name, ftp.path)

    def samefile(self, path1, path2):
        return path1 == path2

    def copy(self, src_url, dst_url):
        # Recursive copy
        if fs.is_dir(src_url):
            fs.mkdir(dst_url)
            for fname in fs.iterdir(src_url):
                fs.copy(urljoin(src_url, fname), urljoin(dst_url, fname))
            return

        if is_ftp(src_url) and is_ftp(dst_url):
            with FtpWrapper(src_url) as src_ftp, \
                    FtpWrapper(dst_url) as dst_ftp:
                with src_ftp.conn.open(src_ftp.path, 'rb') as src, \
                        dst_ftp.conn.open(dst_ftp.path, 'wb') as dst:
                    dst_ftp.conn.copyfileobj(src, dst)
        elif is_ftp(src_url) and is_file(dst_url):
            _, dst_path = splitscheme(dst_url)
            with FtpWrapper(src_url) as src_ftp:
                src_ftp.conn.download(src_ftp.path, dst_path)
        elif is_file(src_url) and is_ftp(dst_url):
            _, src_path = splitscheme(src_url)
            with FtpWrapper(dst_url) as dst_ftp:
                dst_ftp.conn.upload(src_path, dst_ftp.path)
        else:
            raise UnsupportedOperation

    def move(self, src_url, dst_url):
        # Rename on same server
        src_scheme, src_path = splitscheme(src_url)
        dst_scheme, dst_path = splitscheme(dst_url)
        if src_scheme == dst_scheme and commonprefix([src_path, dst_path]):
            # TODO avoid second connection
            with FtpWrapper(src_url) as src_ftp, \
                    FtpWrapper(dst_url) as dst_ftp:
                src_ftp.conn.rename(src_ftp.path, dst_ftp.path)
                return

        fs.copy(src_url, dst_url)
        if fs.exists(src_url):
            fs.delete(src_url)

    def get_stats(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            lstat = ftp.conn.lstat(ftp.path)
            dt_mtime = datetime.utcfromtimestamp(lstat.st_mtime)
            st_mode = stat.filemode(lstat.st_mode)
            self.cache.put(path, 'size_bytes', lstat.st_size)
            self.cache.put(path, 'modified_datetime', dt_mtime)
            self.cache.put(path, 'get_permissions', st_mode)
            self.cache.put(path, 'get_owner', lstat.st_uid)
            self.cache.put(path, 'get_group', lstat.st_gid)


class FtpsFs(FtpFs):
    scheme = 'ftps://'
