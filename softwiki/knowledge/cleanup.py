"""Canonical-aware document deletion/rollback (v0)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from softwiki.knowledge.canonical import mark_wiki_stale_for_topics
from softwiki.knowledge.wiki_queue import enqueue_wiki_rebuild
from softwiki.source_store.models import (
    Adjudication, CanonicalClaim, Claim, ClaimEvidence, Contradiction, Document,
)


def delete_document_knowledge(db: Session, doc_id: int) -> dict:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None:
        raise ValueError("Document not found")
    raw_ids = [row[0] for row in db.query(Claim.id).filter(Claim.document_id == doc_id).all()]
    canonical_ids = {
        row[0] for row in db.query(Claim.canonical_id).filter(
            Claim.document_id == doc_id, Claim.canonical_id.isnot(None)
        ).all()
    }
    topics = {
        row[0] for row in db.query(CanonicalClaim.topic).filter(
            CanonicalClaim.id.in_(canonical_ids)
        ).all()
    } if canonical_ids else set()

    if raw_ids:
        db.query(ClaimEvidence).filter(ClaimEvidence.claim_id.in_(raw_ids)).delete(
            synchronize_session=False
        )
    db.query(ClaimEvidence).filter(ClaimEvidence.document_id == doc_id).delete(
        synchronize_session=False
    )
    db.flush()

    removed_canonical = 0
    for c in db.query(CanonicalClaim).filter(CanonicalClaim.id.in_(canonical_ids)).all():
        remaining = (
            db.query(ClaimEvidence)
            .filter(ClaimEvidence.canonical_id == c.id)
            .order_by(ClaimEvidence.id.asc())
            .all()
        )
        if remaining:
            c.evidence_count = len(remaining)
            first = remaining[0]
            c.primary_document_id = first.document_id
            c.primary_page_start = first.page_start
            c.primary_page_end = first.page_end
            if c.status == "superseded" and c.valid_to is None:
                c.status = "active"
        else:
            rows = db.query(Contradiction).filter(
                (Contradiction.claim_a_id == c.id) | (Contradiction.claim_b_id == c.id)
            ).all()
            ids = [r.id for r in rows]
            if ids:
                db.query(Adjudication).filter(Adjudication.contradiction_id.in_(ids)).delete(
                    synchronize_session=False
                )
                db.query(Contradiction).filter(Contradiction.id.in_(ids)).delete(
                    synchronize_session=False
                )
            db.delete(c)
            removed_canonical += 1
    db.delete(doc)
    db.commit()

    if topics:
        mark_wiki_stale_for_topics(db, topics, reason="document_deleted")
        enqueue_wiki_rebuild(db, topics, reason="document_deleted")
    return {
        "document_id": doc_id,
        "raw_claims": len(raw_ids),
        "canonical_removed": removed_canonical,
        "topics": sorted(topics),
    }
