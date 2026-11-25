"""Durable bulk backfill: queue missing subjects and requeue on restart."""

from datetime import datetime

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


def _seed(db):
    from softwiki.source_store.models import (
        CanonicalClaim, Document, Entity, Relationship,
    )

    doc = Document(title="doc", raw_text="x", cleaned_text="x", hash="h-backfill")
    db.add(doc)
    db.flush()
    hub = Entity(name="Cortex-M55", type="product")
    leaf = Entity(name="Helium", type="feature")
    db.add_all([hub, leaf])
    db.flush()
    db.add(CanonicalClaim(
        id="cc_b1", canonical_key="kb1", text="Cortex-M55 supports Helium.",
        actor="ARM", topic="m55", stance="unclear", confidence=0.9,
        status="active", primary_document_id=doc.id, evidence_count=1,
        subject="Cortex-M55", object="Helium",
    ))
    for i in range(2):
        db.add(Relationship(
            source_name="Cortex-M55", target_name="Helium",
            relation_type="supports", document_id=doc.id, status="active",
            source_entity_id=hub.id, target_entity_id=leaf.id,
            canonical_claim_id="cc_b1",
        ))
    db.commit()


def test_enqueue_missing_subjects(db, monkeypatch):
    import softwiki.wiki.subject_pages as sp
    from softwiki.knowledge.wiki_queue import enqueue_missing_subjects
    from softwiki.source_store.models import WikiRebuildTask

    monkeypatch.setattr(sp, "DEFAULT_MIN_CLAIMS", 1)
    # In a one-subject test corpus every subject is 100% of the library; the
    # "theme" guard would otherwise filter it out.
    monkeypatch.setenv("WIKI_SUBJECT_THEME_SHARE", "2")
    _seed(db)

    created = enqueue_missing_subjects(db, limit=10, min_relations=1)
    assert created >= 1
    tasks = db.query(WikiRebuildTask).filter(WikiRebuildTask.kind == "subject").all()
    assert any(t.topic == "Cortex-M55" for t in tasks)

    # idempotent: a second pass must not duplicate queued subjects
    assert enqueue_missing_subjects(db, limit=10, min_relations=1) == 0


def test_requeue_running_on_start(db):
    from softwiki.knowledge.wiki_queue import requeue_running_on_start
    from softwiki.source_store.models import WikiRebuildTask

    db.add(WikiRebuildTask(topic="SPE", kind="subject", status="running",
                           attempts=1, updated_at=datetime.utcnow()))
    db.commit()

    count = requeue_running_on_start(db)
    row = db.query(WikiRebuildTask).filter(WikiRebuildTask.topic == "SPE").one()
    assert count == 1
    assert row.status == "pending"
    assert row.attempts == 1  # keep the attempt count for max_attempts logic
