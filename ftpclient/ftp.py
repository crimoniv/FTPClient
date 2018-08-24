import errno
import ftplib
import re
import socket
import threading
from urllib.parse import unquote, urlparse

from fman import load_json

import ftputil

from .exceptions import \
    AuthenticationError, HostUnreachableError, TemporaryError

ERRNO_RE = re.compile(r'^\[Errno (-?\d+)\]')


def parse_errno(s):
    match = ERRNO_RE.match(s)
    if match:
        return int(match.group(1))


class FtpSession(ftplib.FTP):
    def __init__(self, host, port, user, password):
        super().__init__()
        self.connect(host, port)
        # FIXME ftplib.error_temp: 421 Too many connections from the
        #       same IP address.
        self.set_pasv(False)
        self.login(user, password)


class FtpTlsSession(ftplib.FTP_TLS):
    def __init__(self, host, port, user, password):
        super().__init__()
        self.connect(host, port)
        self.set_pasv(False)
        self.login(user, password)
        self.prot_p()


class FtpWrapper():
    __conn_pool = {}

    def __init__(self, url):
        u = self._get_bookmark(url)
        self._url = u.geturl()
        self._scheme = '%s://' % (u.scheme,)
        self._path = u.path or '/'
        self._host = u.hostname or ''
        self._port = u.port or 21
        self._user = unquote(u.username or '')
        self._passwd = unquote(u.password or '')

    def __enter__(self):
        if self.hash in self.__conn_pool:
            try:
                self.conn._session.voidcmd('NOOP')
            except Exception:
                pass  # Assume connection timeout
            else:
                return self

        session_factory = \
            FtpTlsSession if self._scheme == 'ftps://' else FtpSession
        try:
            ftp_host = ftputil.FTPHost(
                self._host, self._port, self._user, self._passwd,
                session_factory=session_factory)
        except ftputil.error.TemporaryError as e:
            raise TemporaryError(e.strerror) from e
        except ftputil.error.PermanentError as e:
            # from fman import show_alert
            # show_alert('dir(e) = %s' % (dir(e),))
            # show_alert('type(e) = %s' % (type(e),))
            # show_alert('e.errno = %s' % (e.errno,))
            # show_alert('e.strerror = %s' % (e.strerror,))
            if e.errno == 530:
                raise AuthenticationError(e.strerror) from e
            raise
        except ftputil.error.FTPOSError as e:
            # FIX e.errno == None
            if e.errno is None:
                e.errno = parse_errno(e.strerror)
            if e.errno == errno.EHOSTUNREACH:  # 113
                raise HostUnreachableError(e.strerror) from e
            if e.errno == socket.EAI_NONAME:  # -2
                raise HostUnreachableError(e.strerror) from e
            raise

        self.__conn_pool[self.hash] = ftp_host
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        # try:
        #     self.__conn.quit()
        # except:
        #     pass
        # finally:
        #     self.__conn = None
        return

    def _get_bookmark(self, url):
        u = urlparse(url)
        url_without_path = u._replace(path='').geturl()

        bookmarks = \
            load_json('FTP Bookmarks.json', default={})
        # Replace base URL -if found in bookmarks-, keep the same path
        if url_without_path in bookmarks:
            u = urlparse(bookmarks[url_without_path][0])._replace(path=u.path)

        return u

    @property
    def hash(self):
        return hash((
            threading.get_ident(), self._host, self._port, self._user,
            self._passwd))

    @property
    def conn(self):
        if self.hash not in self.__conn_pool:
            raise Exception('Not connected')
        return self.__conn_pool[self.hash]

    @property
    def path(self):
        return self._path
