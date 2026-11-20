"""Network ACL (SOFTWIKI_ALLOWED_CIDRS) tests.

Perimeter control, not identity. Two rules matter:
  * empty config disables it (backward compatible);
  * a malformed config denies everyone (fail closed).
"""

import pytest

from softwiki import netacl


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("SOFTWIKI_ALLOWED_CIDRS", raising=False)
    monkeypatch.delenv("SOFTWIKI_TRUSTED_CIDRS", raising=False)
    yield


def test_disabled_by_default():
    assert netacl.enabled() is False
    assert netacl.check("203.0.113.5") == (True, None)


def test_allows_listed_cidr(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_CIDRS", "")
    assert netacl.check("203.0.113.7")[0] is True


def test_denies_outside_cidr(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_CIDRS", "")
    ok, reason = netacl.check("198.51.100.9")
    assert ok is False
    assert reason


def test_trusted_peers_bypass(monkeypatch):
    """Docker bridge must always work: the web container proxies /api with it."""
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24")
    assert netacl.check("172.18.0.4")[0] is True
    assert netacl.check("127.0.0.1")[0] is True


def test_narrowed_trusted_list_is_honoured(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_CIDRS", "127.0.0.1/32")
    assert netacl.check("127.0.0.1")[0] is True
    assert netacl.check("172.18.0.4")[0] is False


def test_malformed_allowlist_denies_everyone(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "definitely-not-a-cidr")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_CIDRS", "")
    ok, reason = netacl.check("203.0.113.7")
    assert ok is False
    assert "misconfigured" in (reason or "")


def test_unknown_peer_denied_when_enabled(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_CIDRS", "")
    assert netacl.check(None)[0] is False


def test_ipv4_mapped_address(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_CIDRS", "")
    assert netacl.check("::ffff:203.0.113.8")[0] is True


def test_describe(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ALLOWED_CIDRS", "203.0.113.0/24,198.51.100.1/32")
    info = netacl.describe()
    assert info["enabled"] is True
    assert "203.0.113.0/24" in info["allowed"]
    assert info["allowed_error"] is None
