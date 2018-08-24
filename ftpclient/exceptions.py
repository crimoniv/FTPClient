from ftputil.error import FTPError  # noqa


class FTPClientError(Exception):
    pass


# ftputil.error.PermanentError:
#   530 Authentication failed.
class AuthenticationError(FTPClientError):
    pass


# ftputil.error.FTPOSError:
#   [Errno 113] No route to host
#   [Errno -2] Name or service not known
class HostUnreachableError(FTPClientError):
    pass


# ftputil.error.TemporaryError:
#   421 Unable to read the indexed puredb file (or old format detected)
#   421 5 users (the maximum) are already logged in, sorry
class TemporaryError(FTPClientError):
    pass


# ftputil.error.PermanentError:
#   500 I won't open a connection to ::1%1800 (only to 172.17.0.1)
