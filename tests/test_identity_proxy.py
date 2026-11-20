"""Reverse-proxy auth mode: trust boundary tests.

The whole design rests on one rule: identity headers are believed **only** when
the TCP peer is a configured trusted proxy. If that ever breaks, anyone can
become anyone by sending a header.
"""

import pytest

from softwiki.identity import proxy as px


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "SOFTWIKI_TRUSTED_PROXIES",
        "SOFTWIKI_PROXY_USER_HEADER",
        "SOFTWIKI_PROXY_GROUPS_HEADER",
        "SOFTWIKI_PROXY_EMAIL_HEADER",
        "SOFTWIKI_PROXY_NAME_HEADER",
        "SOFTWIKI_PROXY_ISSUER_LABEL",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_no_trusted_proxies_means_trust_nobody():
    headers = {"x-auth-request-user": "alice"}
    assert px.peer_trusted("172.18.0.5") is False
    assert px.identity_from_headers(headers, "172.18.0.5") is None


def test_headers_ignored_from_untrusted_peer(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "172.18.0.0/16")
    headers = {"x-auth-request-user": "alice"}

    assert px.identity_from_headers(headers, "203.0.113.9") is None
    assert px.identity_from_headers(headers, None) is None


def test_headers_honoured_from_trusted_peer(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "172.18.0.0/16")
    headers = {
        "x-auth-request-user": "alice",
        "x-auth-request-groups": "staff;research,ops",
        "x-auth-request-email": "alice@example.edu",
        "x-auth-request-preferred-username": "Alice W",
    }

    ident = px.identity_from_headers(headers, "172.18.0.7")
    assert ident is not None
    assert ident.subject == "alice"
    assert ident.issuer == "proxy:proxy"
    assert ident.email == "alice@example.edu"
    assert ident.groups == ["ops", "research", "staff"]
    assert ident.display_name == "Alice W"


def test_missing_user_header_is_not_identity(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "127.0.0.1")
    assert px.identity_from_headers({}, "127.0.0.1") is None


def test_malformed_trusted_list_fails_closed(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "not-a-cidr")
    assert px.peer_trusted("127.0.0.1") is False


def test_custom_header_names(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "127.0.0.1")
    monkeypatch.setenv("SOFTWIKI_PROXY_USER_HEADER", "X-Remote-User")
    monkeypatch.setenv("SOFTWIKI_PROXY_ISSUER_LABEL", "campus")

    ident = px.identity_from_headers({"x-remote-user": "bob"}, "127.0.0.1")
    assert ident is not None
    assert ident.subject == "bob"
    assert ident.issuer == "proxy:campus"

    # The default header alone must not work once a custom one is configured.
    assert px.identity_from_headers({"x-auth-request-user": "eve"}, "127.0.0.1") is None


def test_ipv4_mapped_peer_matches_ipv4_rule(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "172.18.0.0/16")
    assert px.peer_trusted("::ffff:172.18.0.9") is True


def test_describe_does_not_leak_secrets(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "172.18.0.0/16")
    info = px.describe()
    assert info["enabled"] is True
    assert info["trusted_proxies"] == ["172.18.0.0/16"]
    assert "sub" not in info
