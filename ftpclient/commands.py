from operator import itemgetter
from urllib.parse import urlparse

from fman import \
    DirectoryPaneCommand, NO, QuicksearchItem, YES, load_json, show_alert, \
    show_prompt, show_quicksearch
from fman.url import splitscheme

from .exceptions import AuthError
from .filesystems import is_ftp


class OpenFtpLocation(DirectoryPaneCommand):
    def __call__(self):
        prompt_text = 'Please enter the URL'
        prompt_default = \
            'ftp[s]://[user[:password]@]ftp.host[:port][/path/to/dir]'
        while True:
            text, ok = show_prompt(prompt_text, default=prompt_default)
            if not text or not ok:
                break
            try:
                self.pane.set_path(text)
            except AuthError as e:
                prompt_text = 'Wrong credentials, please check the URL'
                prompt_default = text


class OpenFtpBookmark(DirectoryPaneCommand):
    def __call__(self):
        result = show_quicksearch(self._get_items)
        if result and result[1]:
            # Fetch bookmarks to connect to the default path
            bookmarks = \
                load_json('FTP Bookmarks.json', default={})
            bookmark = bookmarks[result[1]]
            url = urlparse(result[1])._replace(path=bookmark[1]).geturl()
            self.pane.set_path(url)

    def _get_items(self, query):
        bookmarks = \
            load_json('FTP Bookmarks.json', default={})

        for item in sorted(bookmarks.keys()):
            try:
                index = item.lower().index(query)
            except ValueError:
                continue
            else:
                highlight = range(index, index + len(query))
                yield QuicksearchItem(item, highlight=highlight)


class AddFtpBookmark(DirectoryPaneCommand):
    def __call__(self):
        url = self.pane.get_path()
        if not is_ftp(url):
            url = 'ftp[s]://user[:password]@other.host[:port]/some_dir'

        url, ok = show_prompt(
            'New FTP bookmark, please enter the URL', default=url)

        if not (url and ok):
            return
        if not is_ftp(url):
            show_alert(
                'URL must include any of the following schemes: '
                'ftp://, ftps://')
            return

        bookmarks = \
            load_json('FTP Bookmarks.json', default={}, save_on_quit=True)

        # XXX URL is split in `(base, path)` to allow setting a default path
        u = urlparse(url)
        base = alias = u._replace(path='').geturl()
        path = u.path

        if base in bookmarks:
            # XXX if base URL points to an alias, resolve to an existing URL
            base = bookmarks[base][0]

        if path and path.strip('/'):
            alias += '-'.join(path.split('/'))
        alias, ok = show_prompt(
            'Please enter an alias (will override aliases with the same name)',
            default=alias)

        if not (alias and ok):
            return
        if not is_ftp(alias):
            # XXX alias must include the FTP scheme
            scheme, _ = splitscheme(base)
            alias = scheme + alias
        if urlparse(alias).path:
            show_alert('Aliases should not include path information')
            return

        bookmarks[alias] = (base, path)


class RemoveFtpBookmark(DirectoryPaneCommand):
    def __call__(self):
        result = show_quicksearch(self._get_items)
        if result and result[1]:
            choice = show_alert(
                'Are you sure you want to delete "%s"' % (result[1],),
                buttons=YES | NO,
                default_button=NO
            )
            if choice == YES:
                bookmarks = \
                    load_json('FTP Bookmarks.json', default={}, save_on_quit=True)
                bookmarks.pop(result[1], None)

    def _get_items(self, query):
        bookmarks = \
            load_json('FTP Bookmarks.json', default={})

        for item in sorted(bookmarks.keys()):
            try:
                index = item.lower().index(query)
            except ValueError:
                continue
            else:
                highlight = range(index, index + len(query))
                yield QuicksearchItem(item, highlight=highlight)


class OpenFtpHistory(DirectoryPaneCommand):
    def __call__(self):
        result = show_quicksearch(self._get_items)
        if result and result[1]:
            self.pane.set_path(result[1])

    def _get_items(self, query):
        bookmarks = \
            load_json('FTP History.json', default={})

        for item, _ in sorted(
                bookmarks.items(), key=itemgetter(1), reverse=True):
            try:
                index = item.lower().index(query)
            except ValueError:
                continue
            else:
                highlight = range(index, index + len(query))
                yield QuicksearchItem(item, highlight=highlight)


class RemoveFtpHistory(DirectoryPaneCommand):
    def __call__(self):
        choice = show_alert(
            'Are you sure you want to delete the FTP connection history?',
            buttons=YES | NO,
            default_button=NO
        )
        if choice == YES:
            history = \
                load_json('FTP History.json', default={}, save_on_quit=True)
            history.clear()
