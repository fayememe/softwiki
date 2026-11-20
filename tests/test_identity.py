"""Tests for the identity layer (docs/02-design/auth-oidc.md)."""

import json
import os

import pytest
import yaml
from fastapi.testclient import TestClient

from softwiki.identity import ExternalIdentity, available_adapters, get_adapter
from softwiki.identity.superuser import (
    SuperuserDenied,
    close_superuser,
    is_local_address,
    open_superuser,
    reset_state,
    superuser_session,
)
from softwiki.identity.users import (
    LOCAL_ISSUER,
    LOCAL_SUBJECT,
    IdentityDenied,
    LocalUser,
    UserStore,
    kb_scope_is_empty,
    visible_kbs,
)
from softwiki.permissions import (
    FALLBACK_ROLE,
    allowed_kbs,
    can,
    current_role,
    granted_role,
    min_role,
    normalize_role,
    reset_downgrade,
    reset_role,
    role_level,
    set_downgrade,
    set_role,
)


# -- permissions fail closed --------------------------------------------


def test_unknown_role_falls_back_to_read_only():
    assert normalize_role("wiki-admni") == FALLBACK_ROLE
    assert normalize_role("") == FALLBACK_ROLE
    assert normalize_role(None) == FALLBACK_ROLE
    assert not can("system.admin", "wiki-admni")


def test_role_aliases_still_work():
    assert normalize_role("admin") == "wiki-admin"
    assert normalize_role("study") == "wiki-study"


def test_downgrade_cannot_escalate():
    role_token = set_role("wiki-work")
    down_token = set_downgrade("wiki-admin")
    try:
        assert current_role() == "wiki-work"
    finally:
        reset_downgrade(down_token)
        reset_role(role_token)


def test_downgrade_lowers_effective_role():
    role_token = set_role("wiki-admin")
    down_token = set_downgrade("wiki-study")
    try:
        assert granted_role() == "wiki-admin"
        assert current_role() == "wiki-study"
        assert not can("ingest.write")
    finally:
        reset_downgrade(down_token)
        reset_role(role_token)


def test_min_role_picks_least_privileged():
    assert min_role("wiki-admin", "wiki-study") == "wiki-study"
    assert min_role("wiki-manage", "wiki-work") == "wiki-work"
    assert min_role(None, "garbage") == FALLBACK_ROLE
    assert role_level("wiki-admin") > role_level("wiki-study")


# -- kb scope ------------------------------------------------------------


def test_wildcard_is_a_real_wildcard():
    kbs = ["a-kb", "b-kb"]
    assert allowed_kbs("*", kbs) == kbs
    assert allowed_kbs(None, kbs) == kbs
    # New kb appearing later is covered by the wildcard.
    assert allowed_kbs("*", kbs + ["c-kb"]) == ["a-kb", "b-kb", "c-kb"]


def test_kb_scope_typo_drops_without_raising():
    kbs = ["coffee-kb", "ai-history-kb"]
    assert visible_kbs(["coffe-kb"], kbs) == []
    assert kb_scope_is_empty(["coffe-kb"], kbs) is True
    assert visible_kbs(["coffee-kb"], kbs) == ["coffee-kb"]
    assert kb_scope_is_empty(["coffee-kb"], kbs) is False


# -- adapters ------------------------------------------------------------


def test_builtin_adapters_present():
    assert {"oidc", "wechat"} <= set(available_adapters())


def test_oidc_claims_to_identity():
    adapter = get_adapter("oidc")
    identity = adapter.identity_from_claims(
        "oidc:school",
        {"sub": "u-1", "email": "a@b.edu", "name": "Alice", "groups": ["staff"]},
    )
    assert identity.issuer == "oidc:school"
    assert identity.subject == "u-1"
    assert identity.groups == ["staff"]
    assert identity.display_name == "Alice"


def test_oidc_requires_subject():
    with pytest.raises(ValueError):
        get_adapter("oidc").identity_from_claims("oidc:school", {"email": "a@b"})


def test_wechat_identity_has_no_groups():
    adapter = get_adapter("wechat")
    identity = adapter.identity_from_claims("wechat:site", {"openid": "o-123", "nickname": "张三"})
    assert identity.subject == "o-123"
    assert identity.groups == []
    assert identity.display_name == "张三"


def test_identity_rejects_missing_key():
    with pytest.raises(ValueError):
        ExternalIdentity(issuer="", subject="x")


# -- user store ----------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    return UserStore(path=str(tmp_path / "config" / "users.yaml"))


def test_upsert_is_idempotent(store):
    identity = ExternalIdentity(issuer="oidc:school", subject="u-1", email="a@b.edu")
    first = store.upsert(identity)
    second = store.upsert(ExternalIdentity(issuer="oidc:school", subject="u-1", email="a2@b.edu"))
    assert first.created_at is not None
    assert second.email == "a2@b.edu"
    assert len(store.load()) == 1


def test_subject_is_scoped_by_issuer(store):
    store.upsert(ExternalIdentity(issuer="oidc:school", subject="same", email="x"))
    store.upsert(ExternalIdentity(issuer="wechat:site", subject="same", email="y"))
    assert len(store.load()) == 2


def test_unmapped_user_is_pending_by_default(store, monkeypatch):
    monkeypatch.delenv("SOFTWIKI_UNKNOWN_USER_POLICY", raising=False)
    authz = store.authorize(ExternalIdentity(issuer="oidc:s", subject="u", groups=["strangers"]))
    assert authz.pending is True
    assert authz.granted_role == FALLBACK_ROLE


def test_mapping_selects_role(store, monkeypatch):
    monkeypatch.delenv("SOFTWIKI_UNKNOWN_USER_POLICY", raising=False)
    store.save_mapping({"softwiki-admin": ["wiki-admin"], "softwiki-study": ["wiki-study"]})
    authz = store.authorize(
        ExternalIdentity(issuer="oidc:s", subject="u", groups=["softwiki-admin", "softwiki-study"])
    )
    assert authz.granted_role == "wiki-admin"
    assert authz.pending is False


def test_override_beats_mapping(store, monkeypatch):
    monkeypatch.delenv("SOFTWIKI_UNKNOWN_USER_POLICY", raising=False)
    store.save_mapping({"softwiki-admin": ["wiki-admin"]})
    store.upsert(ExternalIdentity(issuer="oidc:s", subject="u", groups=["softwiki-admin"]))
    store.update("oidc:s", "u", role_override="wiki-study")
    authz = store.authorize(ExternalIdentity(issuer="oidc:s", subject="u", groups=["softwiki-admin"]))
    assert authz.granted_role == "wiki-study"


def test_unknown_policy_deny_refuses(store, monkeypatch):
    monkeypatch.setenv("SOFTWIKI_UNKNOWN_USER_POLICY", "deny")
    with pytest.raises(IdentityDenied):
        store.authorize(ExternalIdentity(issuer="oidc:s", subject="u"))


def test_unknown_policy_lowest_grants_read_only(store, monkeypatch):
    monkeypatch.setenv("SOFTWIKI_UNKNOWN_USER_POLICY", "lowest")
    authz = store.authorize(ExternalIdentity(issuer="oidc:s", subject="u"))
    assert authz.granted_role == FALLBACK_ROLE
    assert authz.pending is False


def test_local_disable_wins_over_mapping(store, monkeypatch):
    monkeypatch.delenv("SOFTWIKI_UNKNOWN_USER_POLICY", raising=False)
    store.save_mapping({"admins": ["wiki-admin"]})
    store.upsert(ExternalIdentity(issuer="oidc:s", subject="u", groups=["admins"]))
    store.update("oidc:s", "u", is_active=False)
    with pytest.raises(IdentityDenied):
        store.authorize(ExternalIdentity(issuer="oidc:s", subject="u", groups=["admins"]))


def test_mapping_typo_role_degrades_to_read_only(store):
    store.save_mapping({"g": ["wiki-admn"]})
    assert store.mapping()["g"] == [FALLBACK_ROLE]


# -- superuser -----------------------------------------------------------


def test_local_address_detection():
    assert is_local_address("127.0.0.1")
    assert is_local_address("::1")
    assert is_local_address("::ffff:127.0.0.1")
    assert not is_local_address("10.1.2.3")
    assert not is_local_address("172.18.0.5")
    assert not is_local_address(None)


def test_superuser_in_single_machine_mode_is_always_on(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "off")
    reset_state()
    session = open_superuser(source_ip="10.1.2.3")
    assert session.describe()["active"] is True
    reset_state()


def test_remote_open_requires_ttl(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "local")
    monkeypatch.setenv("SOFTWIKI_SUPERUSER_TOKEN", "s3cret")
    reset_state()
    with pytest.raises(SuperuserDenied):
        open_superuser(source_ip="10.1.2.3", token="s3cret")
    session = open_superuser(source_ip="10.1.2.3", token="s3cret", ttl="30m")
    assert session.ttl_seconds == 1800
    reset_state()


def test_remote_open_needs_configured_token(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "local")
    monkeypatch.delenv("SOFTWIKI_SUPERUSER_TOKEN", raising=False)
    reset_state()
    with pytest.raises(SuperuserDenied):
        open_superuser(source_ip="10.1.2.3", ttl="10m")
    reset_state()


def test_superuser_window_expires(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "local")
    monkeypatch.setenv("SOFTWIKI_SUPERUSER_TOKEN", "s3cret")
    reset_state()
    open_superuser(source_ip="127.0.0.1", token="s3cret", ttl=0.01)
    import time

    time.sleep(0.05)
    assert superuser_session() is None
    reset_state()


def test_superuser_close(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "off")
    reset_state()
    open_superuser(source_ip="127.0.0.1")
    assert superuser_session() is not None
    close_superuser()
    assert superuser_session() is None
    reset_state()


# -- HTTP surface --------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    workspace = tmp_path / "kb"
    (workspace / ".softwiki" / "index").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    monkeypatch.setenv("SOFTWIKI_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.delenv("SOFTWIKI_AUTH_MODE", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("SOFTWIKI_SUPERUSER_TOKEN", raising=False)
    reset_state()
    from softwiki.api.server import app

    yield TestClient(app)
    reset_state()


def test_permissions_endpoint_reports_effective_role(client):
    body = client.get("/api/permissions").json()
    assert body["role"] == "wiki-admin"
    downgraded = client.get("/api/permissions", headers={"X-SoftWiki-Downgrade": "wiki-study"})
    assert downgraded.json()["role"] == "wiki-study"


def test_downgrade_cannot_escalate_over_http(client):
    response = client.post("/api/auth/downgrade", json={"role": "wiki-admin"})
    assert response.status_code == 200
    # A downgraded session cannot lift its own constraint...
    escalated = client.post(
        "/api/auth/downgrade",
        json={"role": "wiki-admin"},
        headers={"X-SoftWiki-Downgrade": "wiki-study"},
    )
    assert escalated.status_code == 403
    # ...but clearing the downgrade returns the granted role.
    cleared = client.request(
        "DELETE", "/api/auth/downgrade", headers={"X-SoftWiki-Downgrade": "wiki-study"}
    )
    assert cleared.json()["effective_role"] == "wiki-admin"


def test_downgraded_admin_loses_admin_surfaces(client):
    response = client.get("/api/admin/users", headers={"X-SoftWiki-Downgrade": "wiki-study"})
    assert response.status_code == 403


def test_single_machine_mode_needs_no_login(client):
    assert client.get("/api/admin/users").status_code == 200


def test_verified_mode_requires_identity(client, monkeypatch):
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "local")
    assert client.get("/api/admin/users").status_code == 401
    # The superuser route stays reachable so an operator can rescue the box.
    assert client.get("/api/auth/superuser").status_code == 200


def test_write_requests_are_audited_and_reads_are_not(client, tmp_path):
    audit_path = tmp_path / "audit.log"
    client.post("/api/auth/downgrade", json={"role": "wiki-study"})
    client.get("/api/permissions")
    records = [json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()]
    actions = [r["action"] for r in records]
    assert "POST /api/auth/downgrade" in actions
    assert not any(a.startswith("GET ") for a in actions)
    assert all(r["identity"] == f"{LOCAL_ISSUER}:{LOCAL_SUBJECT}" for r in records)


def test_admin_can_manage_mapping(client):
    put = client.put("/api/admin/mapping", json={"groups": {"staff": ["wiki-work"]}})
    assert put.status_code == 200
    assert client.get("/api/admin/mapping").json()["groups"] == {"staff": ["wiki-work"]}


def test_admin_user_patch_rejects_unknown_role(client, monkeypatch):
    store = UserStore()
    store.upsert(ExternalIdentity(issuer="oidc:s", subject="u"))
    bad = client.patch("/api/admin/users/oidc:s/u", json={"role_override": "wiki-god"})
    assert bad.status_code == 400
    good = client.patch("/api/admin/users/oidc:s/u", json={"kb_scope": ["coffee-kb"]})
    assert good.status_code == 200
    assert good.json()["kb_scope"] == ["coffee-kb"]


def test_admin_users_flags_empty_scope(client):
    from softwiki.kb.registry_state import _is_kb_dir  # noqa: F401 - documents intent

    store = UserStore()
    store.upsert(ExternalIdentity(issuer="oidc:s", subject="typo"))
    store.update("oidc:s", "typo", kb_scope=["definitely-not-a-kb"])
    workspace = os.environ["WORKSPACES_ROOT"]
    os.makedirs(os.path.join(workspace, "real-kb", ".softwiki"), exist_ok=True)
    rows = client.get("/api/admin/users").json()["users"]
    row = next(r for r in rows if r["subject"] == "typo")
    assert row["visible_kbs"] == []
    assert row["kb_scope_empty"] is True


def test_login_route_rejects_single_machine_mode(client):
    response = client.post("/api/auth/login", json={"provider": "oidc", "claims": {"sub": "x"}})
    assert response.status_code == 400
