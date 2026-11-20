"""Tests for the graph overview / subgraph endpoints.

The graph panel used to render every entity and relationship at once, which
froze the browser on real corpora. These endpoints exist so the panel can draw a
small, expandable neighbourhood instead.
"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    workspace = tmp_path / "graph-kb"
    (workspace / ".softwiki" / "index").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    monkeypatch.setenv("SOFTWIKI_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.delenv("SOFTWIKI_AUTH_MODE", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)
    from softwiki.api.server import app

    return TestClient(app)


def _seed():
    from softwiki.source_store.db import SessionLocal
    from softwiki.source_store.models import Document, Entity, Relationship

    db = SessionLocal()
    try:
        doc = Document(
            title="graph seed",
            raw_text="x",
            cleaned_text="x",
            hash="graph-seed-hash",
        )
        db.add(doc)
        db.flush()

        hub = "Cortex-M55"
        leaves = ["DSP", "NPU", "Ethos-U55", "Helium"]
        for name in [hub, *leaves]:
            db.add(Entity(name=name, type="concept", description=f"about {name}"))
        for leaf in leaves:
            db.add(
                Relationship(
                    source_name=hub,
                    target_name=leaf,
                    relation_type="supports",
                    document_id=doc.id,
                    confidence=0.9,
                    status="active",
                )
            )
        # An unrelated island, so the seed picks the hub by degree.
        db.add(Entity(name="Unrelated", type="concept"))
        db.commit()
        return doc.id
    finally:
        db.close()


def test_overview_returns_a_drawable_subset(client):
    _seed()
    body = client.get("/api/graph/overview?limit=5").json()
    names = {entity["name"] for entity in body["entities"]}
    assert "Cortex-M55" in names
    assert len(body["entities"]) <= 5
    assert body["total_entities"] >= 6
    assert body["total_relationships"] >= 4
    # Degree is exposed so the panel can size hubs.
    hub = next(e for e in body["entities"] if e["name"] == "Cortex-M55")
    assert hub["degree"] >= 4


def test_overview_on_empty_graph(client):
    body = client.get("/api/graph/overview").json()
    assert body["entities"] == []
    assert body["relationships"] == []
    assert body["total_entities"] == 0


def test_subgraph_expands_one_hop(client):
    _seed()
    body = client.get("/api/graph/subgraph?entity=DSP&depth=1").json()
    names = {entity["name"] for entity in body["entities"]}
    assert {"DSP", "Cortex-M55"} <= names
    assert body["root"] == "DSP"
    assert body["truncated"] is False
    # Only edges touching the neighbourhood come back.
    for rel in body["relationships"]:
        assert rel["source_name"] in names
        assert rel["target_name"] in names


def test_subgraph_requires_an_entity(client):
    assert client.get("/api/graph/subgraph?entity=").status_code == 400


def test_subgraph_clamps_depth(client):
    _seed()
    body = client.get("/api/graph/subgraph?entity=Cortex-M55&depth=99").json()
    assert body["root"] == "Cortex-M55"
