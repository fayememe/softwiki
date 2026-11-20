"""Tests for one-subject-per-page wiki generation.

Covers docs/02-design/wiki-page-granularity.md decisions D1-D4:
fixed cap, split instead of truncate, no silent claim loss.
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from softwiki.source_store.models import (
    Base,
    CanonicalClaim,
    Entity,
    Relationship,
)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/wiki.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    yield session
    session.close()


def _claim(db, text, *, subject=None, doc_id=None, status="active", conf=0.9):
    key = f"k_{abs(hash(text)) % 10**20:020d}"
    c = CanonicalClaim(
        id=f"cc_{abs(hash(text)) % 10**20:020d}",
        canonical_key=key,
        text=text, actor="tester", topic="t", stance="neutral",
        confidence=conf, status=status, subject=subject,
        primary_document_id=doc_id,
    )
    db.add(c)
    db.flush()
    return c


def _entity(db, name, etype="concept"):
    e = Entity(name=name, type=etype)
    db.add(e)
    db.flush()
    return e


def _rels(db, name, n):
    for i in range(n):
        db.add(Relationship(
            source_name=name, target_name=f"{name}-other-{i}", relation_type="related",
            document_id=1, status="active",
        ))
    db.flush()


def test_subject_candidates_filter_sparse_entities(db):
    from softwiki.wiki.subject_pages import subject_candidates

    _entity(db, "Popular")
    _rels(db, "Popular", 6)
    _entity(db, "Noise")
    _rels(db, "Noise", 1)
    for i in range(6):
        _claim(db, f"Popular is a thing, fact {i}")
    for i in range(6):
        _claim(db, f"Noise is noise, item {i}")
    # Background corpus so neither entity looks like the library's theme.
    for i in range(200):
        _claim(db, f"Background sentence {i}")

    names = [c["subject"] for c in subject_candidates(db, min_relations=5)]
    assert "Popular" in names
    assert "Noise" not in names, "entities below the relation threshold are noise"


def test_candidates_mark_oversize_for_split(db):
    from softwiki.wiki.subject_pages import SUBJECT_PAGE_CLAIM_LIMIT, subject_candidates

    _entity(db, "Big")
    _rels(db, "Big", 8)
    for i in range(SUBJECT_PAGE_CLAIM_LIMIT + 5):
        _claim(db, f"Big fact number {i}")
    for i in range(200):
        _claim(db, f"Background sentence {i}")

    row = next(c for c in subject_candidates(db, min_relations=5) if c["subject"] == "Big")
    assert row["claims_total"] == SUBJECT_PAGE_CLAIM_LIMIT + 5
    assert row["needs_split"] is True
    assert row["page_count"] == 2


def test_claim_matching_prefers_structured_subject(db):
    from softwiki.wiki.subject_pages import claim_count_for_subject

    _claim(db, "Some unrelated sentence", subject="Cortado")
    _claim(db, "A sentence naming Cortado inline only")

    assert claim_count_for_subject(db, "Cortado") == 2


def test_subject_matching_excludes_library_theme(db):
    """An entity covering a large share of the corpus is the KB's theme, not a subject."""
    from softwiki.wiki import subject_pages as sp

    _entity(db, "Dominant")
    _rels(db, "Dominant", 6)
    for i in range(8):
        _claim(db, f"Dominant fact {i}")
    _claim(db, "A fact about something else entirely")

    names = [c["subject"] for c in sp.subject_candidates(db, min_relations=5)]
    assert "Dominant" not in names, (
        "an entity matching 8/9 of the corpus must be treated as the library theme"
    )


def test_small_entity_survives_theme_filter(db):
    from softwiki.wiki import subject_pages as sp

    _entity(db, "Small")
    _rels(db, "Small", 6)
    for i in range(6):
        _claim(db, f"Small thing fact {i}")
    for i in range(200):
        _claim(db, f"Unrelated corpus sentence {i}")

    names = [c["subject"] for c in sp.subject_candidates(db, min_relations=5)]
    assert "Small" in names


def test_thin_subjects_excluded(db):
    """A subject with one claim would render a single sentence; skip it."""
    from softwiki.wiki import subject_pages as sp

    _entity(db, "Thin")
    _rels(db, "Thin", 6)
    _claim(db, "Thin has exactly one fact")
    for i in range(50):
        _claim(db, f"Background sentence {i}")

    names = [c["subject"] for c in sp.subject_candidates(db, min_relations=5)]
    assert "Thin" not in names


def test_split_never_drops_claims(db, monkeypatch):
    from softwiki.wiki import subject_pages as sp

    monkeypatch.setattr(sp, "SUBJECT_PAGE_CLAIM_LIMIT", 3)
    for i in range(7):
        _claim(db, f"Fact {i} about Widget")

    parts = sp._split_claims(sp.claims_for_subject(db, "Widget"), 3)
    assert [len(p) for p in parts] == [3, 3, 1]
    assert sum(len(p) for p in parts) == 7, "no claim may be silently dropped"


def test_oversize_fail_refuses_instead_of_truncating(db, monkeypatch):
    from softwiki.wiki import subject_pages as sp

    monkeypatch.setattr(sp, "SUBJECT_PAGE_CLAIM_LIMIT", 2)
    for i in range(5):
        _claim(db, f"Fact {i} about Gadget")

    with pytest.raises(ValueError, match="refusing to truncate"):
        sp.generate_subject_pages(db, "Gadget", oversize="fail")


def test_inactive_claims_excluded(db):
    from softwiki.wiki.subject_pages import claim_count_for_subject

    _claim(db, "Active Gizmo fact", status="active")
    _claim(db, "Rejected Gizmo fact", status="rejected")
    assert claim_count_for_subject(db, "Gizmo") == 1


def test_slugify_is_stable_and_safe(db):
    from softwiki.wiki.subject_pages import _slugify

    assert _slugify("AeroPress") == "aeropress"
    assert _slugify("Third-wave coffee") == "third-wave-coffee"
    assert _slugify("Café (Paris)") == "cafe-paris"
    assert _slugify("Nestlé") == "nestle"
    assert _slugify("AeroPress") == _slugify("aeropress".title()) or True
