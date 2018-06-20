from fman.fs import Column, query

from .filesystems import is_ftp


class Permissions(Column):
    display_name = 'Permissions'

    def get_str(self, url):
        if is_ftp(url):
            return str(query(url, 'get_permissions'))


class Owner(Column):
    display_name = 'Owner'

    def get_str(self, url):
        if is_ftp(url):
            return str(query(url, 'get_owner'))


class Group(Column):
    display_name = 'Group'

    def get_str(self, url):
        if is_ftp(url):
            return str(query(url, 'get_group'))
