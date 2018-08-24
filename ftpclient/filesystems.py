import errno
import re
import stat
from datetime import datetime
from io import UnsupportedOperation
from os.path import commonprefix, join as pathjoin
from tempfile import NamedTemporaryFile

from fman import fs, show_alert, show_status_message
from fman.fs import FileSystem, cached
from fman.url import join as urljoin, splitscheme

from .exceptions import FTPClientError, FTPError, TemporaryError
from .ftp import FtpWrapper

is_ftp = re.compile('^ftps?://').match
is_file = re.compile('^file://').match


def tmp_exc_to_status(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        # except TemporaryError as e:
        #     show_status_message(str(e))
        # except (FTPClientError, FTPError) as e:
        #     show_alert(str(e))
        except Exception:
            raise
    return wrapper


class FtpFs(FileSystem):
    scheme = 'ftp://'

    def get_default_columns(self, path):
        return (
            'core.Name', 'core.Size', 'core.Modified',
            'ftpclient.columns.Permissions', 'ftpclient.columns.Owner',
            'ftpclient.columns.Group')

    @cached
    @tmp_exc_to_status
    def size_bytes(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.path.getsize(ftp.path)

    @cached
    @tmp_exc_to_status
    def modified_datetime(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return datetime.utcfromtimestamp(ftp.conn.path.getmtime(ftp.path))

    @cached
    @tmp_exc_to_status
    def get_permissions(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return stat.filemode(ftp.conn.lstat(ftp.path).st_mode)

    @cached
    @tmp_exc_to_status
    def get_owner(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.lstat(ftp.path).st_uid

    @cached
    @tmp_exc_to_status
    def get_group(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.lstat(ftp.path).st_gid

    @cached
    @tmp_exc_to_status
    def exists(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.path.exists(ftp.path)

    @cached
    @tmp_exc_to_status
    def is_dir(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            return ftp.conn.path.isdir(ftp.path)

    @tmp_exc_to_status
    def iterdir(self, path):
        # XXX avoid errors on URLs without connection details
        if not path:
            return
        show_status_message('Loading %s...' % (path,))
        with FtpWrapper(self.scheme + path) as ftp:
            for name in ftp.conn.listdir(ftp.path):
                self.get_stats(pathjoin(path, name))
                yield name
        show_status_message('Ready.', timeout_secs=0)

    @tmp_exc_to_status
    def delete(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            if self.is_dir(path):
                ftp.conn.rmtree(ftp.path)
            else:
                ftp.conn.remove(ftp.path)

    @tmp_exc_to_status
    def move_to_trash(self, path):
        # ENOSYS: Function not implemented
        raise OSError(errno.ENOSYS, "FTP has no Trash support")

    @tmp_exc_to_status
    def mkdir(self, path):
        with FtpWrapper(self.scheme + path) as ftp:
            ftp.conn.makedirs(ftp.path)

    @tmp_exc_to_status
    def touch(self, path):
        if self.exists(path):
            raise OSError(errno.EEXIST, "File exists")
        with FtpWrapper(self.scheme + path) as ftp:
            with NamedTemporaryFile(delete=True) as tmp:
                ftp.conn.upload(tmp.name, ftp.path)

    @tmp_exc_to_status
    def samefile(self, path1, path2):
        return path1 == path2

    @tmp_exc_to_status
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

    @tmp_exc_to_status
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

    @tmp_exc_to_status
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
