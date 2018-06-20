# Copyright (C) 2014-2016, Stefan Schwarzer <sschwarzer@sschwarzer.net>
# and ftputil contributors (see `doc/contributors.txt`)
# See the file LICENSE for licensing terms.

"""
Unit tests for session factory helpers.
"""

from __future__ import unicode_literals

import ftputil.session


class MockSession(object):
    """
    Mock session base class to determine if all expected calls
    have happened.
    """

    def __init__(self):
        self.calls = []

    def add_call(self, *args):
        self.calls.append(args)

    def connect(self, host, port):
        self.add_call("connect", host, port)

    def _fix_socket(self):
        self.add_call("_fix_socket")

    def set_debuglevel(self, value):
        self.add_call("set_debuglevel", value)

    def login(self, user, password):
        self.add_call("login", user, password)

    def set_pasv(self, flag):
        self.add_call("set_pasv", flag)


class EncryptedMockSession(MockSession):

    def auth_tls(self):
        self.add_call("auth_tls")

    def prot_p(self):
        self.add_call("prot_p")


class TestSessionFactory(object):
    """
    Test if session factories created by
    `ftputil.session.session_factory` trigger the expected calls.
    """

    def test_defaults(self):
        """Test defaults (apart from base class)."""
        factory = \
          ftputil.session.session_factory(base_class=MockSession)
        session = factory("host", "user", "password")
        assert (session.calls ==
                [("connect", "host", 21), ("login", "user", "password")])

    def test_different_port(self):
        """Test setting the command channel port with `port`."""
        factory = \
          ftputil.session.session_factory(base_class=MockSession, port=2121)
        session = factory("host", "user", "password")
        assert (session.calls ==
                [("connect", "host", 2121), ("login", "user", "password")])

    def test_use_passive_mode(self):
        """
        Test explicitly setting passive/active mode with
        `use_passive_mode`.
        """
        # Passive mode
        factory = ftputil.session.session_factory(base_class=MockSession,
                                                  use_passive_mode=True)
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("login", "user", "password"),
                                 ("set_pasv", True)]
        # Active mode
        factory = ftputil.session.session_factory(base_class=MockSession,
                                                  use_passive_mode=False)
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("login", "user", "password"),
                                 ("set_pasv", False)]

    def test_encrypt_data_channel(self):
        """Test request to call `prot_p` with `encrypt_data_channel`."""
        # With encrypted data channel (default for encrypted session).
        factory = ftputil.session.session_factory(
                    base_class=EncryptedMockSession)
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("login", "user", "password"),
                                 ("prot_p",)]
        #
        factory = ftputil.session.session_factory(
                    base_class=EncryptedMockSession, encrypt_data_channel=True)
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("login", "user", "password"),
                                 ("prot_p",)]
        # Without encrypted data channel.
        factory = ftputil.session.session_factory(
                    base_class=EncryptedMockSession, encrypt_data_channel=False)
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("login", "user", "password")]

    def test_debug_level(self):
        """Test setting the debug level on the session."""
        factory = ftputil.session.session_factory(base_class=MockSession,
                                                  debug_level=1)
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("set_debuglevel", 1),
                                 ("login", "user", "password")]

    def test_m2crypto_session(self):
        """Test call sequence for M2Crypto session."""
        factory = \
          ftputil.session.session_factory(base_class=EncryptedMockSession)
        # Return `True` to fake that this is a session deriving from
        # `M2Crypto.ftpslib.FTP_TLS`.
        factory._use_m2crypto_ftpslib = lambda self: True
        # Override `_fix_socket` here, not in `MockSession`. Since
        # the created session class _inherits_ from `MockSession`,
        # it would override the `_fix_socket` there.
        factory._fix_socket = lambda self: self.add_call("_fix_socket")
        session = factory("host", "user", "password")
        assert session.calls == [("connect", "host", 21),
                                 ("auth_tls",),
                                 ("_fix_socket",),
                                 ("login", "user", "password"),
                                 ("prot_p",)]
