import os
import shutil
from datetime import datetime

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    from softwiki.source_store.db import init_tables, SessionLocal, get_engine
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


def _doc(db, title, url, published, family=None):
    from softwiki.source_store.models import Document
    d = Document(
        title=title, url=url, source_name="ARM", source_type="manual",
        raw_text=title, cleaned_text=title, hash=f"h-{title}-{published}",
        published_at=published, collected_at=published, family_id=family,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _claim(db, doc, cid, text, topic="pl031", actor="ARM", stance="unclear"):
    from softwiki.source_store.models import Claim
    c = Claim(
        id=cid, document_id=doc.id, text=text, actor=actor, topic=topic,
        stance=stance, confidence=0.9, published_at=doc.published_at,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_canonicalize_merges_duplicate_claims(db):
    from softwiki.knowledge.canonical import canonicalize_claim, backfill_canonical_claims
    from softwiki.source_store.models import CanonicalClaim, ClaimEvidence
    d1 = _doc(db, "A", "https://x/a", datetime(2024, 1, 1))
    d2 = _doc(db, "B", "https://x/b", datetime(2024, 1, 2))
    c1 = _claim(db, d1, "c1", "RTCDR is a 32-bit read-only register at offset 0x000.")
    c2 = _claim(db, d2, "c2", "RTCDR is a 32-bit read-only register at offset 0x000.")
    cc1 = canonicalize_claim(db, c1, d1)
    cc2 = canonicalize_claim(db, c2, d2)
    assert cc1.id == cc2.id
    assert db.query(CanonicalClaim).count() == 1
    assert db.query(ClaimEvidence).count() == 2
    assert db.query(CanonicalClaim).first().evidence_count == 2


def test_version_supersede_is_automatic(db):
    from softwiki.knowledge.versioning import assign_document_version
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.conflicts import scan_conflicts
    from softwiki.source_store.models import CanonicalClaim, Contradiction
    d1 = _doc(db, "PL031 TRM", "https://x/pl031", datetime(2020, 1, 1))
    d2 = _doc(db, "PL031 TRM", "https://x/pl031", datetime(2024, 1, 1))
    assign_document_version(db, d1); assign_document_version(db, d2); db.commit()
    assert d1.family_id == d2.family_id
    assert d2.supersedes_document_id == d1.id
    c1 = _claim(db, d1, "v1", "The RTCCR reset value is 0x0.")
    c2 = _claim(db, d2, "v2", "The RTCCR reset value is 0x1.")
    cc1 = canonicalize_claim(db, c1, d1)
    cc2 = canonicalize_claim(db, c2, d2)
    scan_conflicts(db)
    db.refresh(cc1); db.refresh(cc2)
    assert cc1.status == "superseded"
    assert cc2.status == "active"
    row = db.query(Contradiction).first()
    assert row is not None
    assert row.type == "version_update"
    assert row.auto_resolved is True


def test_source_conflict_requires_adjudication(db):
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.conflicts import scan_conflicts, adjudicate
    from softwiki.knowledge.versioning import assign_document_version
    from softwiki.source_store.models import CanonicalClaim, Contradiction
    d1 = _doc(db, "Vendor A", "https://a/doc", datetime(2024, 1, 1))
    d2 = _doc(db, "Vendor B", "https://b/doc", datetime(2024, 1, 1))
    assign_document_version(db, d1); assign_document_version(db, d2); db.commit()
    c1 = _claim(db, d1, "a1", "The RTCCR reset value is 0x0.")
    c2 = _claim(db, d2, "b1", "The RTCCR reset value is 0x1.")
    cc1 = canonicalize_claim(db, c1, d1)
    cc2 = canonicalize_claim(db, c2, d2)
    scan_conflicts(db)
    db.refresh(cc1); db.refresh(cc2)
    assert cc1.status == "disputed"
    assert cc2.status == "disputed"
    row = db.query(Contradiction).first()
    assert row is not None and row.type == "source_conflict" and row.auto_resolved is False
    result = adjudicate(db, row.id, "accept_b", actor="reviewer", reason="newer source")
    db.refresh(cc1); db.refresh(cc2)
    assert result["status"] == "resolved"
    assert cc1.status == "superseded"
    assert cc2.status == "active"


def test_metrics_returns_canonical_counts(db):
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.conflicts import metrics
    d = _doc(db, "A", "https://x/a", datetime(2024, 1, 1))
    c = _claim(db, d, "c1", "RTCDR is at 0x000.")
    canonicalize_claim(db, c, d)
    m = metrics(db)
    assert m["raw_claims"] == 1
    assert m["canonical_claims"] == 1
    assert m["evidence"] >= 1


def test_claim_topic_maps_to_curated_page(monkeypatch, tmp_path):
    import yaml
    cfg = tmp_path / "topics.yaml"
    cfg.write_text(yaml.safe_dump({
        "pl031": {"name": "PL031", "kind": "page", "aliases": ["rtc-*"]},
        "amba": {"name": "AMBA", "kind": "page", "aliases": ["apb-*"]},
    }), encoding="utf-8")
    from softwiki.wiki.interventions import page_topics_for_claim_topic
    monkeypatch.setattr("softwiki.wiki.interventions.get_config_path", lambda name: str(cfg) if name == "topics.yaml" else str(tmp_path / name))
    assert page_topics_for_claim_topic("rtc-register-map") == ["pl031"]
    assert page_topics_for_claim_topic("apb-interface") == ["amba"]
    assert page_topics_for_claim_topic("unknown-topic") == []


def test_adjudication_reprojects_graph_and_timeline(db):
    from datetime import datetime
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.conflicts import scan_conflicts, adjudicate
    from softwiki.knowledge.versioning import assign_document_version
    from softwiki.source_store.models import CanonicalClaim, Contradiction, Event, Relationship
    d1 = _doc(db, "Vendor A", "https://a/doc", datetime(2024, 1, 1))
    d2 = _doc(db, "Vendor B", "https://b/doc", datetime(2024, 1, 1))
    assign_document_version(db, d1); assign_document_version(db, d2); db.commit()
    c1 = _claim(db, d1, "a1", "The RTCCR reset value is 0x0.")
    c2 = _claim(db, d2, "b1", "The RTCCR reset value is 0x1.")
    cc1 = canonicalize_claim(db, c1, d1)
    cc2 = canonicalize_claim(db, c2, d2)
    rel = Relationship(source_name="RTCCR", target_name="reset", relation_type="has_value",
                       document_id=d1.id, confidence=0.9, canonical_claim_id=cc1.id)
    ev = Event(title="RTCCR reset", event_date=datetime(2024, 1, 1), document_id=d1.id,
               canonical_claim_id=cc1.id)
    db.add_all([rel, ev]); db.commit()
    scan_conflicts(db)
    row = db.query(Contradiction).first()
    assert row is not None
    adjudicate(db, row.id, "accept_b", actor="reviewer")
    db.refresh(rel); db.refresh(ev)
    assert rel.status == "superseded"
    assert ev.status == "superseded"


def test_wiki_rebuild_queue_dedup(db, monkeypatch):
    from softwiki.knowledge.wiki_queue import enqueue_wiki_rebuild, pending_count
    from softwiki.source_store.models import WikiRebuildTask
    monkeypatch.setattr(
        "softwiki.wiki.interventions.page_topics_for_claim_topic",
        lambda topic: ["pl031"] if topic == "rtc-register-map" else [],
    )
    assert enqueue_wiki_rebuild(db, ["rtc-register-map"], reason="test") == 1
    assert enqueue_wiki_rebuild(db, ["rtc-register-map"], reason="test2") == 0
    assert db.query(WikiRebuildTask).count() == 1
    assert pending_count(db)["pending"] == 1


def test_wiki_artifact_history_archive(db, tmp_path):
    from softwiki.wiki.page_generator import WikiPageGenerator
    from softwiki.source_store.models import WikiArtifactVersion
    md = tmp_path / "pl031.md"
    js = tmp_path / "pl031.json"
    md.write_text("# old\n\nold content\n", encoding="utf-8")
    js.write_text('{"claim_ids":["a","b"],"intervention_hash":"p1"}', encoding="utf-8")
    gen = WikiPageGenerator()
    gen._archive_previous(db, "pl031", str(md), None, str(js))
    rows = db.query(WikiArtifactVersion).all()
    assert len(rows) == 1
    assert rows[0].topic == "pl031"
    assert "old content" in rows[0].content
    # Archiving the same content again is idempotent.
    gen._archive_previous(db, "pl031", str(md), None, str(js))
    assert db.query(WikiArtifactVersion).count() == 1


def test_structured_conflict_same_subject_predicate(db):
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.conflicts import scan_conflicts
    from softwiki.source_store.models import CanonicalClaim, Contradiction
    d1 = _doc(db, "A", "https://a/x", datetime(2024, 1, 1))
    d2 = _doc(db, "B", "https://b/x", datetime(2024, 1, 1))
    c1 = _claim(db, d1, "s1", "RTCCR reset value is 0x0.")
    c2 = _claim(db, d2, "s2", "The RTCCR reset value equals 0x1.")
    a = canonicalize_claim(db, c1, d1)
    b = canonicalize_claim(db, c2, d2)
    for c, obj in ((a, "0x0"), (b, "0x1")):
        c.subject = "RTCCR"; c.predicate = "reset value"; c.object = obj; c.qualifiers = "{}"
    db.commit()
    scan_conflicts(db)
    row = db.query(Contradiction).first()
    assert row is not None and row.type == "source_conflict"


def test_nli_judge_service_applies_contradiction(db):
    from datetime import datetime
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.nli import judge_candidates
    from softwiki.source_store.models import Contradiction
    d1 = _doc(db, "A", "https://a/nli", datetime(2024, 1, 1))
    d2 = _doc(db, "B", "https://b/nli", datetime(2024, 1, 1))
    c1 = _claim(db, d1, "n1", "The RTCCR reset value is 0x0.")
    c2 = _claim(db, d2, "n2", "The RTCCR reset value is 0x1.")
    a = canonicalize_claim(db, c1, d1)
    b = canonicalize_claim(db, c2, d2)
    def fake_judge(a, b, da, db_doc):
        return {"verdict": "contradiction", "severity": "medium", "reason": "test"}
    result = judge_candidates(db, limit=5, apply=True, judge=fake_judge)
    assert result["applied"] is True
    db.refresh(a); db.refresh(b)
    assert a.status == "disputed" and b.status == "disputed"
    assert db.query(Contradiction).filter(Contradiction.type == "source_conflict").count() == 1


def test_citation_check():
    from softwiki.intelligence.citation_check import verify_citations
    cits = [{"num": 1}, {"num": 2}]
    r = verify_citations("Claim [1] and unsupported [3].", cits)
    assert r["unknown"] == [3]
    assert r["unused"] == [2]
    assert r["warnings"]


def test_permissions_role_capabilities():
    from softwiki.permissions import can, normalize_role, role_capabilities
    assert normalize_role("work") == "wiki-work"
    assert normalize_role("study") == "wiki-study"
    assert can("read.ask", "wiki-study")
    assert not can("ingest.write", "wiki-study")
    assert not can("ingest.write", "wiki-work")
    assert can("wiki.build", "wiki-work")
    assert can("ingest.write", "wiki-manage")
    assert can("system.admin", "wiki-admin")
    assert "read.*" in role_capabilities("wiki-study")


def test_deleting_document_cleans_canonical_and_evidence(db):
    from datetime import datetime
    from softwiki.knowledge.canonical import canonicalize_claim
    from softwiki.knowledge.cleanup import delete_document_knowledge
    from softwiki.source_store.models import CanonicalClaim, ClaimEvidence, Document, Relationship
    d = _doc(db, "Delete me", "https://x/delete", datetime(2024, 1, 1))
    c = _claim(db, d, "del1", "RTCDR is at offset 0x000.")
    cc = canonicalize_claim(db, c, d)
    rel = Relationship(source_name="RTCDR", target_name="offset", relation_type="is",
                       document_id=d.id, confidence=0.9, canonical_claim_id=cc.id)
    db.add(rel); db.commit()
    result = delete_document_knowledge(db, d.id)
    assert result["document_id"] == d.id
    assert db.query(Document).filter(Document.id == d.id).first() is None
    assert db.query(CanonicalClaim).filter(CanonicalClaim.id == cc.id).first() is None
    assert db.query(ClaimEvidence).filter(ClaimEvidence.document_id == d.id).count() == 0
