import ftplib
import threading
from urllib.parse import unquote, urlparse

from fman import load_json

try:
    import ftputil
except ImportError:
    import os
    import sys
    sys.path.append(
        os.path.join(os.path.dirname(__file__), 'ftputil-3.4'))
    import ftputil

from .exceptions import AuthError


class FtpSession(ftplib.FTP):
    def __init__(self, host, port, user, password):
        super().__init__()
        self.connect(host, port)
        # FIXME ftplib.error_temp: 421 Too many connections from the
        #       same IP address.
        self.login(user, password)


class FtpTlsSession(ftplib.FTP_TLS):
    def __init__(self, host, port, user, password):
        super().__init__()
        self.connect(host, port)
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
        except ftputil.error.PermanentError as e:
            if e.errno == 530:
                raise AuthError(e.strerror) from e
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
