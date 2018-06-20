from os.path import basename
from tempfile import NamedTemporaryFile

from core.commands import _open_local_file

from fman import DirectoryPaneListener, fs, show_alert, YES, NO, load_json
from fman.url import splitscheme

from .filesystems import is_ftp


class FtpListener(DirectoryPaneListener):
    def on_command(self, command_name, args):
        if command_name != 'open_file':
            return

        url = args['url']
        scheme, path = splitscheme(url)
        if not is_ftp(scheme):
            return

        tmp = NamedTemporaryFile(prefix=basename(path), delete=False)
        tmp_path = tmp.name
        tmp_url = 'file://' + tmp_path

        fs.copy(url, tmp_url)
        _open_local_file(tmp_path)
        choice = show_alert(
            'Upload modified file?',
            buttons=YES | NO,
            default_button=YES
        )

        if choice == YES:
            fs.move(tmp_url, url)

        return 'reload', {}

    def on_path_changed(self):
        url = self.pane.get_path()
        if not is_ftp(url):
            return
        scheme, path = splitscheme(url)
        if not path:
            # XXX avoid storing URLs with empty path
            return
        history = \
            load_json('FTP History.json', default={}, save_on_quit=True)
        history[url] = history.get(url, 0) + 1
