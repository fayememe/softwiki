"""Built-in admin account: hashing, first-run creation, login throttling.

The account exists so an installation is usable before any identity provider is
wired up, and so an operator can get back in when that provider is down. The
tests below pin the properties that make that safe.
"""

import os

import pytest

from softwiki.identity import localauth
from softwiki.identity.localauth import (
    LoginRateLimiter,
    authenticate,
    ensure_builtin_admin,
    hash_password,
    set_builtin_admin_password,
    verify_password,
)
from softwiki.identity.users import UserStore


@pytest.fixture(autouse=True)
def _workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    monkeypatch.delenv("SOFTWIKI_ADMIN_PASSWORD", raising=False)
    localauth.LOGIN_LIMITER.reset()
    yield


def test_hash_is_not_plaintext_and_verifies():
    digest = hash_password("correct horse battery")
    assert "correct horse battery" not in digest
    assert digest.startswith("scrypt$")
    assert verify_password("correct horse battery", digest) is True
    assert verify_password("wrong", digest) is False


def test_same_password_gets_different_salt():
    a, b = hash_password("same-password-123"), hash_password("same-password-123")
    assert a != b, "a shared salt would let one crack attack all accounts"


def test_malformed_hash_never_verifies():
    for bad in ("", None, "plain", "scrypt$x$y$z$q$w", "md5$abc"):
        assert verify_password("anything", bad) is False


def test_first_run_generates_a_password_when_env_missing():
    created, generated = ensure_builtin_admin()
    assert created is True
    assert generated and len(generated) >= 12, "a random password must be produced"
    store = UserStore()
    admin = store.find(localauth.ISSUER, localauth.SUBJECT)
    assert admin is not None
    assert admin.role_override == "wiki-admin"
    assert verify_password(generated, admin.password_hash)


def test_first_run_uses_env_password(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_ADMIN_PASSWORD", "env-provided-pass-1")
    created, generated = ensure_builtin_admin()
    assert created is True
    assert generated is None, "an operator-supplied password must not be echoed"
    admin = UserStore().find(localauth.ISSUER, localauth.SUBJECT)
    assert verify_password("env-provided-pass-1", admin.password_hash)


def test_second_run_does_not_reset_the_password(monkeypatch):
    ensure_builtin_admin()
    monkeypatch.setenv("SOFTWIKI_ADMIN_PASSWORD", "a-different-password")
    created, generated = ensure_builtin_admin()
    assert created is False and generated is None
    admin = UserStore().find(localauth.ISSUER, localauth.SUBJECT)
    assert verify_password("a-different-password", admin.password_hash) is False


def test_short_passwords_rejected():
    with pytest.raises(ValueError):
        set_builtin_admin_password("short")


def test_authenticate_only_accepts_the_builtin_admin():
    set_builtin_admin_password("a-long-enough-pass")
    assert authenticate("admin", "a-long-enough-pass") is not None
    assert authenticate("admin", "nope") is None
    assert authenticate("someone-else", "a-long-enough-pass") is None


def test_inactive_admin_cannot_log_in():
    set_builtin_admin_password("a-long-enough-pass")
    store = UserStore()
    users = store.load()
    for u in users:
        if u.key == (localauth.ISSUER, localauth.SUBJECT):
            u.is_active = False
    store.save(users)
    assert authenticate("admin", "a-long-enough-pass") is None


def test_rate_limiter_blocks_after_threshold():
    limiter = LoginRateLimiter(attempts=3, window_seconds=60)
    assert all(limiter.allow("203.0.113.9") for _ in range(3))
    assert limiter.allow("203.0.113.9") is False
    # A different peer is unaffected.
    assert limiter.allow("203.0.113.10") is True


def test_login_updates_last_login():
    set_builtin_admin_password("a-long-enough-pass")
    user = authenticate("admin", "a-long-enough-pass")
    assert user.last_login_at
    stored = UserStore().find(localauth.ISSUER, localauth.SUBJECT)
    assert stored.last_login_at == user.last_login_at
