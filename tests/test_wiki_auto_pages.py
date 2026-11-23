"""Auto reconcile: queue the entity pages that need generating.

Rules under test:
  * a fresh kb (no generated pages) enqueues the first batch => "新建库立即可用"
  * afterwards only subjects whose claim count changed are queued
  * budget caps a run, and already-queued subjects are not duplicated
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from softwiki.source_store.models import Base, CanonicalClaim, Entity, Relationship, WikiRebuildTask


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/auto.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("WIKI_AUTO_INITIAL_SUBJECTS", raising=False)
    monkeypatch.delenv("WIKI_AUTO_MAX_SUBJECTS", raising=False)
    # A tiny corpus would make every entity look like the library theme.
    monkeypatch.setenv("WIKI_SUBJECT_THEME_SHARE", "0.9")
    yield session
    session.close()


def _seed(db, name, claims, relations=6, offset=0):
    db.add(Entity(name=name, type="concept"))
    for i in range(relations):
        db.add(Relationship(source_name=name, target_name=f"{name}-x{i}",
                            relation_type="related", document_id=1, status="active"))
    for i in range(claims):
        db.add(CanonicalClaim(
            id=f"cc_{name.replace(' ', '_')}_{offset}_{i}",
            canonical_key=f"k_{name}_{offset}_{i}",
            text=f"{name} fact number {i}",
            actor="t", topic="t", stance="neutral", confidence=0.9, status="active",
        ))
    db.flush()


def _background(db, n=300):
    """Unrelated claims so no single entity looks like the whole corpus."""
    for i in range(n):
        db.add(CanonicalClaim(
            id=f"cc_bg_{i}", canonical_key=f"k_bg_{i}",
            text=f"background sentence {i}",
            actor="t", topic="t", stance="neutral", confidence=0.5, status="active",
        ))
    db.flush()


def _tasks(db):
    return db.query(WikiRebuildTask).filter(WikiRebuildTask.kind == "subject").all()


def test_fresh_kb_enqueues_first_batch(db, monkeypatch):
    _background(db)
    _seed(db, "Alpha", 8)
    _seed(db, "Beta", 8)
    monkeypatch.setenv("WIKI_AUTO_INITIAL_SUBJECTS", "5")

    from softwiki.wiki.auto_pages import reconcile

    result = reconcile(db)
    assert result["initial"] is True
    assert result["enqueued"] == 2
    assert {t.topic for t in _tasks(db)} == {"Alpha", "Beta"}
    assert all(t.status == "pending" for t in _tasks(db))


def test_budget_is_respected(db, monkeypatch):
    _background(db)
    for i in range(6):
        _seed(db, f"S{i}", 8)
    monkeypatch.setenv("WIKI_AUTO_INITIAL_SUBJECTS", "2")

    from softwiki.wiki.auto_pages import reconcile

    assert reconcile(db)["enqueued"] == 2


def test_second_run_does_not_duplicate(db, monkeypatch):
    _background(db)
    _seed(db, "Alpha", 8)
    monkeypatch.setenv("WIKI_AUTO_INITIAL_SUBJECTS", "5")

    from softwiki.wiki.auto_pages import reconcile

    first = reconcile(db)
    second = reconcile(db)
    assert first["enqueued"] == 1
    assert second["enqueued"] == 0, "still pending: must not queue twice"
    assert len(_tasks(db)) == 1


def test_changed_subject_only_after_pages_exist(db, monkeypatch, tmp_path):
    """Once pages exist, reconcile is incremental: only changed counts queue."""
    import json

    _background(db)
    _seed(db, "Alpha", 8)
    _seed(db, "Beta", 8)
    monkeypatch.setenv("WIKI_AUTO_MAX_SUBJECTS", "10")

    # Pretend Alpha already has a page with 8 claims.
    pages_dir = tmp_path / "exports" / "wiki" / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "index.json").write_text(json.dumps({"subjects": [
        {"subject": "Alpha", "slug": "alpha", "claims_total": 8, "pages": ["alpha"]},
    ]}))

    from softwiki.wiki.auto_pages import reconcile

    assert reconcile(db)["enqueued"] == 0, "nothing changed yet"

    # Three more claims for the same entity (no second Entity row).
    for i in range(3):
        db.add(CanonicalClaim(
            id=f"cc_more_{i}", canonical_key=f"k_more_{i}",
            text=f"Alpha extra fact {i}",
            actor="t", topic="t", stance="neutral", confidence=0.9, status="active",
        ))
    db.flush()
    result = reconcile(db)
    assert result["enqueued"] == 1
    assert [t.topic for t in _tasks(db)] == ["Alpha"]


def test_incremental_pass_never_bootstraps(db, monkeypatch):
    """The worker's periodic pass must not create the first pages by itself."""
    _background(db)
    _seed(db, "Alpha", 8)

    from softwiki.wiki.auto_pages import reconcile

    result = reconcile(db, allow_initial=False)
    assert result["enqueued"] == 0
    assert result.get("needs_start") is True
    assert _tasks(db) == []
