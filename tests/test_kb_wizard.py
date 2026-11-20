"""Tests for the kb wizard, kb registry and graph endpoints."""

import os

import pytest
import yaml
from fastapi.testclient import TestClient

from softwiki.kb.registry_state import (
    KbRegistry,
    create_kb,
    plan_create,
    validate_kb_name,
)


def _touch_kb(root: str, name: str, **meta) -> str:
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, ".softwiki", "index"), exist_ok=True)
    os.makedirs(os.path.join(path, "config"), exist_ok=True)
    if meta:
        with open(os.path.join(path, "config", "meta.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f)
    return path


# -- naming --------------------------------------------------------------


@pytest.mark.parametrize("name", ["coffee-kb", "ai_history", "v1.2", "A" * 64])
def test_valid_names(name):
    assert validate_kb_name(name) == name


@pytest.mark.parametrize("name", ["", "  ", ".hidden", "with space", "slash/name", "A" * 65])
def test_invalid_names(name):
    with pytest.raises(ValueError):
        validate_kb_name(name)


# -- registry ------------------------------------------------------------


def test_directories_without_registry_count_as_registered(tmp_path):
    """Deployments predating this module must not lose every kb."""
    root = str(tmp_path / "ws")
    _touch_kb(root, "old-kb")
    registry = KbRegistry(root)
    assert registry.registered_names() == ["old-kb"]
    assert not os.path.exists(registry.path)


def test_unregister_hides_but_keeps_files(tmp_path):
    root = str(tmp_path / "ws")
    _touch_kb(root, "demo-kb")
    registry = KbRegistry(root)
    registry.register("demo-kb", description="demo")
    registry.unregister("demo-kb", unregistered_by="tester")

    assert registry.registered_names() == []
    record = registry.record("demo-kb")
    assert record.status == "unregistered"
    assert record.unregistered_by == "tester"
    # The whole point: nothing on disk was touched.
    assert os.path.isdir(os.path.join(root, "demo-kb", ".softwiki"))

    registry.register("demo-kb")
    assert registry.registered_names() == ["demo-kb"]


def test_register_requires_a_real_kb_dir(tmp_path):
    registry = KbRegistry(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        registry.register("ghost-kb")


# -- plan / create --------------------------------------------------------


def test_plan_does_not_touch_disk(tmp_path):
    root = str(tmp_path / "ws")
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    plan = plan_create("new-kb", description="d", root=root)
    assert not os.path.exists(os.path.join(root, "new-kb"))
    assert plan.name == "new-kb"
    assert {step.kind for step in plan.steps} >= {"directory", "config", "scope", "registry"}
    assert plan.warnings == []


def test_create_writes_config_and_registers(tmp_path):
    root = str(tmp_path / "ws")
    plan = plan_create("new-kb", description="demo kb", root=root)
    result = create_kb(plan, created_by="tester", root=root)

    assert result["name"] == "new-kb"
    kb_path = os.path.join(root, "new-kb")
    with open(os.path.join(kb_path, "config", "meta.yaml"), encoding="utf-8") as f:
        meta = yaml.safe_load(f)
    assert meta["name"] == "new-kb"
    assert meta["description"] == "demo kb"
    assert os.path.isfile(os.path.join(kb_path, "scope.md"))
    assert KbRegistry(root).registered_names() == ["new-kb"]


def test_create_applies_template(tmp_path):
    root = str(tmp_path / "ws")
    plan = plan_create("r-kb", template="research-report", root=root)
    create_kb(plan, root=root)
    with open(os.path.join(root, "r-kb", "config", "topics.yaml"), encoding="utf-8") as f:
        topics = yaml.safe_load(f)["topics"]
    assert "policy" in topics


def test_unknown_template_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        plan_create("x-kb", template="does-not-exist", root=str(tmp_path))


# -- http ----------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    root = str(tmp_path / "ws")
    os.makedirs(root, exist_ok=True)
    monkeypatch.setenv("WORKSPACES_ROOT", root)
    monkeypatch.setenv("WORKSPACE_DIR", os.path.join(root, "wizard-kb"))
    monkeypatch.setenv("SOFTWIKI_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.delenv("SOFTWIKI_AUTH_MODE", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)
    _touch_kb(root, "wizard-kb")
    from softwiki.api.server import app

    return TestClient(app)


def test_wizard_dry_run_then_create(client):
    dry = client.post(
        "/api/kb/create", json={"name": "fresh-kb", "description": "x", "dry_run": True}
    )
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True
    assert not os.path.exists(
        os.path.join(os.environ["WORKSPACES_ROOT"], "fresh-kb", "config")
    )

    real = client.post(
        "/api/kb/create", json={"name": "fresh-kb", "description": "x", "dry_run": False}
    )
    assert real.status_code == 200
    assert real.json()["result"]["name"] == "fresh-kb"


def test_wizard_rejects_bad_name(client):
    assert client.post("/api/kb/create", json={"name": "../escape"}).status_code == 400


def test_kb_listing_respects_registry(client):
    root = os.environ["WORKSPACES_ROOT"]
    _touch_kb(root, "other-kb", description="other")
    names = [kb["name"] for kb in client.get("/api/kb").json()["kbs"]]
    assert "other-kb" in names

    assert client.post("/api/kb/other-kb/unregister").status_code == 200
    names = [kb["name"] for kb in client.get("/api/kb").json()["kbs"]]
    assert "other-kb" not in names
    assert os.path.isdir(os.path.join(root, "other-kb", ".softwiki"))

    assert client.post("/api/kb/other-kb/register").status_code == 200
    names = [kb["name"] for kb in client.get("/api/kb").json()["kbs"]]
    assert "other-kb" in names


def test_unregister_is_audited(client, tmp_path):
    import json

    client.post("/api/kb/wizard-kb/unregister")
    records = [
        json.loads(line)
        for line in (tmp_path / "audit.log").read_text().splitlines()
        if line.strip()
    ]
    assert any(r["action"] == "kb.unregister" for r in records)


def test_kb_scope_filters_listing(tmp_path, monkeypatch):
    """A user limited to one kb must not see the others."""
    root = str(tmp_path / "scope-ws")
    os.makedirs(root, exist_ok=True)
    for name in ("wizard-kb", "visible-kb", "hidden-kb"):
        _touch_kb(root, name)
    monkeypatch.setenv("WORKSPACES_ROOT", root)
    monkeypatch.setenv("WORKSPACE_DIR", os.path.join(root, "wizard-kb"))
    monkeypatch.setenv("SOFTWIKI_AUDIT_LOG", str(tmp_path / "scope-audit.log"))
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "local")
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)

    from softwiki.api.server import app
    from softwiki.identity import ExternalIdentity
    from softwiki.identity.users import UserStore

    store = UserStore()
    store.upsert(ExternalIdentity(issuer="oidc:s", subject="limited"))
    signed_in = store.find("oidc:s", "limited")
    assert signed_in is not None
    signed_in.kb_scope = ["visible-kb"]
    store.save([*[u for u in store.load() if u.key != signed_in.key], signed_in])
    store.upsert(ExternalIdentity(issuer="oidc:s", subject="typo"))
    typo = store.find("oidc:s", "typo")
    assert typo is not None
    typo.kb_scope = ["visble-kb"]
    store.save([*[u for u in store.load() if u.key != typo.key], typo])

    limited = TestClient(app)
    limited.cookies.set("softwiki_identity", '{"issuer": "oidc:s", "subject": "limited"}')
    names = [kb["name"] for kb in limited.get("/api/kb").json()["kbs"]]
    assert names == ["visible-kb"]

    typo = TestClient(app)
    typo.cookies.set("softwiki_identity", '{"issuer": "oidc:s", "subject": "typo"}')
    assert typo.get("/api/kb").json()["kbs"] == []

    # /api/kb is readable without signing in so the UI can probe it; with no
    # identity there is no scope to apply, so it must not leak a filtered list.
    anonymous = TestClient(app)
    assert anonymous.get("/api/kb").status_code == 200
