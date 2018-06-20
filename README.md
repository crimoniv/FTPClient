# FTPClient

A [fman](https://fman.io/) FTP Client that uses the powerful [ftputil](https://ftputil.sschwarzer.net) library.

## Usage

### Commands

- **Open ftp location** (`open_ftp_location`): Connect to a FTP server using the given URL.
- **Add ftp bookmark** (`add_ftp_bookmark`): Bookmark current -or custom- URL.
- **Open ftp bookmark** (`open_ftp_bookmark`): Open a bookmarked URL.
- **Remove ftp bookmark** (`remove_ftp_bookmark`): Remove a bookmarked URL.
- **Open ftp history** (`open_ftp_history`): Open a previous URL.
- **Remove ftp history** (`remove_ftp_history`): Remove the whole connection history.

### Connection URL

The URL must follow the format below:

```
ftp[s]://[user[:password]@]ftp.host[:port][/path/to/dir]
```

## Features
- Support for URL-encoded chars in user/password (e.g. `@` -> `%40`).
- Show extra file/directory attributes: **Permissions**, **Owner** and **Group**.
- Connection pool under the hood for a better overall performance.
- Bookmarks.
- History.
- File view/edit.

## TODO
- Allow setting file/folder permissions, if applicable.
- Limit number of simultaneous connections to avoid `ftplib.error_temp: 421 Too many connections from the same IP address.`.

## Known issues
- Currently there is no way to close an active connection.
- When editing files, there is no way to know if a file has been edited. Must be uploaded manually through the popup.
- **Create file** command shows an **editing files is not supported** alert after file creation, although file edition is enabled.
- When in the root directory, the **Go Up** command raises an error.
- **Move to trash** has been disabled on purpose, there is no Trash support.
- Although there is -theoretically- **FTP_TLS** support, it has not been tested.
- Passwords are stored in plain text when creating Bookmarks.
- Passwords are shown in plain text in the URL (this can be mitigated using Bookmarks).
- Currently `ftputil` is loaded from a frozen copy included in the plugin source pointing to the **3.4** version. I have not found a better way to include it.

## History

See the [CHANGELOG](CHANGELOG.md).

## Credits

- Michael Herrmann ([@mherrmann](https://github.com/mherrmann)), the [fman](https://fman.io/) author.
- Stefan Schwarzer ([@sschwarzer](https://pypi.org/user/sschwarzer/)), the [ftputil](https://ftputil.sschwarzer.net) author.

## License

See the [LICENSE](LICENSE.md) file for license rights and limitations (MIT).
