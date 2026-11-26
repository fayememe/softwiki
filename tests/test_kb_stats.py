"""Tests for `GET /api/kb/stats`.

The home dashboard used to show only the active workspace. Once an instance can
serve several knowledge bases (one directory each under WORKSPACES_ROOT), the
overview has to read every kb's own database — and must mark the ones this
instance cannot open as unavailable instead of reporting zero documents.
"""

import os

import pytest
from fastapi.testclient import TestClient


def _make_kb(root, name, *, with_schema=True):
    path = os.path.join(str(root), name)
    os.makedirs(os.path.join(path, ".softwiki", "index"), exist_ok=True)
    os.makedirs(os.path.join(path, "config"), exist_ok=True)
    db_file = os.path.join(path, ".softwiki", "processed.db")
    if not with_schema:
        return path
    with open(db_file, "wb"):
        pass

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from softwiki.source_store.db import Base
    from softwiki.source_store.models import Document

    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add(Document(title=f"{name} doc", raw_text="x", cleaned_text="x", hash=f"{name}-hash"))
        session.commit()
    finally:
        session.close()
        engine.dispose()
    return path


@pytest.fixture()
def client(tmp_path, monkeypatch):
    workspace = tmp_path / "active-kb"
    (workspace / ".softwiki" / "index").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    monkeypatch.setenv("SOFTWIKI_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.delenv("DATABASE_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_MODE", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)

    from softwiki.api import server

    server._kb_stats_cache.clear()
    from softwiki.kb.health import invalidate

    invalidate()
    return TestClient(server.app)


def test_stats_lists_every_kb_with_counts(client, tmp_path):
    _make_kb(tmp_path, "active-kb")
    _make_kb(tmp_path, "other-kb")

    body = client.get("/api/kb/stats").json()

    names = {kb["name"] for kb in body["kbs"]}
    assert names == {"active-kb", "other-kb"}
    assert body["active"] == "active-kb"
    active = next(kb for kb in body["kbs"] if kb["name"] == "active-kb")
    assert active["active"] is True
    assert active["available"] is True
    assert active["counts"]["documents"] == 1
    # Totals aggregate only kbs that could be read.
    assert body["totals"]["documents"] == 2


def test_unreadable_kb_is_unavailable_not_zero(client, tmp_path):
    _make_kb(tmp_path, "active-kb")
    # A directory without a database, i.e. never created in this instance.
    broken = _make_kb(tmp_path, "broken-kb", with_schema=False)
    assert os.path.isdir(broken)

    body = client.get("/api/kb/stats").json()

    broken_entry = next(kb for kb in body["kbs"] if kb["name"] == "broken-kb")
    assert broken_entry["available"] is False
    assert broken_entry["reason"]
    assert broken_entry["counts"] is None
    assert body["totals"]["documents"] == 1
