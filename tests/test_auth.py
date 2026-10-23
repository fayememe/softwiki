from softwiki.auth import create_token, hash_password, verify_password, verify_token


def test_password_roundtrip():
    stored = hash_password("secret")
    assert verify_password("secret", stored)
    assert not verify_password("wrong", stored)


def test_token_roundtrip(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_SECRET_KEY", "test-secret")
    assert verify_token(create_token("alice", ttl_seconds=60)) == "alice"


def test_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_SECRET_KEY", "test-secret")
    assert verify_token(create_token("alice", ttl_seconds=60) + "x") is None


def test_token_expiry(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_SECRET_KEY", "test-secret")
    assert verify_token(create_token("alice", ttl_seconds=-1)) is None
