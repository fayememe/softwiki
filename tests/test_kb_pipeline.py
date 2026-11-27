"""/api/kb/pipeline must expose in-flight work, not just totals.

The page is the only place an operator can see what is running: extraction
status per document, the wiki queue with topic names, and whether an index
rebuild is currently happening.
"""

import os

import pytest
from fastapi.testclient import TestClient


def _make_kb(root, name):
    path = os.path.join(str(root), name)
    os.makedirs(os.path.join(path, ".softwiki", "index"), exist_ok=True)
    os.makedirs(os.path.join(path, "config"), exist_ok=True)
    with open(os.path.join(path, ".softwiki", "processed.db"), "wb"):
        pass

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from softwiki.source_store.db import Base
    from softwiki.source_store.models import Document, WikiRebuildTask

    engine = create_engine(f"sqlite:///{path}/.softwiki/processed.db")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(Document(title="doc", raw_text="x", cleaned_text="x", hash="h", status="extracting"))
        db.add(WikiRebuildTask(topic="RRAM macro", kind="subject", status="running", attempts=1))
        db.add(WikiRebuildTask(topic="LOAD", kind="subject", status="pending", attempts=0))
        db.commit()
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    workspace = tmp_path / "kb"
    (workspace / ".softwiki" / "index").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    monkeypatch.setenv("SOFTWIKI_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.delenv("DATABASE_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_MODE", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)
    _make_kb(tmp_path, "kb")

    from softwiki.api import server

    server._pipeline_cache.clear()
    return TestClient(server.app)


def test_pipeline_reports_in_flight_work(client):
    body = client.get("/api/kb/pipeline").json()

    assert body["documents"]["in_progress"]["extracting"] == 1
    assert body["documents"]["unfinished"] == 1

    active = body["wiki"]["active"]
    assert {t["topic"] for t in active} == {"RRAM macro", "LOAD"}
    assert {t["status"] for t in active} == {"running", "pending"}
    assert body["index"]["building"] is None
