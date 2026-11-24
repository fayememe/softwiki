"""Schema v3 graph normalization: entity merge, aliases, edge weights."""

import json

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    from softwiki.source_store.db import SessionLocal, get_engine, init_tables

    try:
        get_engine().dispose()
    except Exception:
        pass
    init_tables()
    session = SessionLocal()
    yield session
    session.close()
    try:
        get_engine().dispose()
    except Exception:
        pass


def _doc(db, title):
    from softwiki.source_store.models import Document

    doc = Document(
        title=title, raw_text=title, cleaned_text=title, hash=f"h-{title}",
        source_name="ARM",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_normalize_merges_case_variants_and_aliases(db):
    from scripts.graph_normalize import normalize
    from softwiki.source_store.models import Entity, EntityAlias, Relationship

    d1 = _doc(db, "doc1")
    d2 = _doc(db, "doc2")
    big = Entity(name="Cortex-M55", type="product", description="core")
    small = Entity(name="cortex m55", type="product", description="dup")
    alias_ent = Entity(
        name="Helium", type="feature",
        aliases=json.dumps(["MVE"]),
    )
    db.add_all([big, small, alias_ent])
    db.flush()
    db.add_all([
        Relationship(source_name="Cortex-M55", target_name="Helium",
                     relation_type="supports", document_id=d1.id, status="active",
                     confidence=0.9),
        Relationship(source_name="cortex m55", target_name="Helium",
                     relation_type="supports", document_id=d2.id, status="active",
                     confidence=0.8),
    ])
    db.commit()

    stats = normalize(db)
    assert stats["merged"] == 1
    assert stats["relationships_unresolved"] == 0

    canonical = db.query(Entity).filter(Entity.name == "Cortex-M55").one()
    duplicate = db.query(Entity).filter(Entity.name == "cortex m55").one()
    assert duplicate.merged_into == canonical.id

    helium = db.query(Entity).filter(Entity.name == "Helium").one()
    aliases = {row.normalized for row in db.query(EntityAlias).filter(EntityAlias.entity_id == helium.id)}
    assert "mve" in aliases

    rels = db.query(Relationship).all()
    assert all(rel.source_entity_id == canonical.id for rel in rels)
    assert all(rel.target_entity_id == helium.id for rel in rels)
    # Same (source, target, type) across two documents -> weight 2.
    assert {rel.weight for rel in rels} == {2.0}
    assert {rel.evidence_count for rel in rels} == {2}


def test_normalize_is_idempotent(db):
    from scripts.graph_normalize import normalize
    from softwiki.source_store.models import Entity, Relationship

    doc = _doc(db, "d")
    db.add(Entity(name="AMBA AXI", type="protocol", aliases=json.dumps(["AXI"])))
    db.flush()
    db.add(Relationship(source_name="AMBA AXI", target_name="AMBA AXI",
                        relation_type="includes", document_id=doc.id, status="active"))
    db.commit()

    first = normalize(db)
    second = normalize(db)
    assert second["merged"] == 0
    assert second["relationships_unresolved"] == 0
    assert first["edge_groups"] == second["edge_groups"] == 1
