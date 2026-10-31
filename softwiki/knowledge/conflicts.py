"""Conflict detection and human adjudication (v0)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from softwiki.knowledge.canonical import mark_wiki_stale_for_topics, normalize_text
from softwiki.source_store.models import (
    Adjudication,
    CanonicalClaim,
    ClaimEvidence,
    Contradiction,
    Document,
    WikiArtifactState,
)

MAX_GROUP = 240
_VALUE_RE = re.compile(r"0x[0-9a-f]+|(?<![a-z0-9])\d+(?:\.\d+)?(?![a-z0-9])", re.IGNORECASE)


def _single_value_template(text: str):
    """Conservative v0: only claims with exactly one number/hex value.

    Replace that value with # and require the rest of the sentence to be
    identical. This avoids treating different scenarios (Google vs Microsoft,
    regular vs injected, 22ULL vs 5LPE) as contradictions.
    """
    matches = list(_VALUE_RE.finditer(text or ""))
    if len(matches) != 1:
        return None
    m = matches[0]
    value = m.group(0).lower()
    template = (text[:m.start()] + "#" + text[m.end():])
    return normalize_text(template), value


def _doc(db: Session, canonical: CanonicalClaim) -> Optional[Document]:
    if not canonical.primary_document_id:
        return None
    return db.query(Document).filter(Document.id == canonical.primary_document_id).first()


def _rank(doc: Optional[Document]) -> tuple:
    if doc is None:
        return (datetime.min, 0)
    return (doc.published_at or doc.collected_at or datetime.min, doc.id or 0)


def _existing(db: Session, a_id: str, b_id: str, ctype: str) -> Optional[Contradiction]:
    x, y = sorted([a_id, b_id])
    return (
        db.query(Contradiction)
        .filter(
            Contradiction.claim_a_id == x,
            Contradiction.claim_b_id == y,
            Contradiction.type == ctype,
        )
        .first()
    )


def _create(db: Session, a: CanonicalClaim, b: CanonicalClaim, ctype: str,
            severity: str = "medium", auto: bool = False,
            resolution: str = "") -> Optional[Contradiction]:
    x, y = sorted([a.id, b.id])
    if _existing(db, x, y, ctype):
        return None
    row = Contradiction(
        claim_a_id=x,
        claim_b_id=y,
        type=ctype,
        severity=severity,
        status="auto_resolved" if auto else "open",
        auto_resolved=auto,
        resolution=resolution or None,
        resolved_at=datetime.utcnow() if auto else None,
    )
    db.add(row)
    return row


def _compare(db: Session, a: CanonicalClaim, b: CanonicalClaim) -> Optional[Contradiction]:
    if a.id == b.id:
        return None
    if a.status not in ("active", "disputed") or b.status not in ("active", "disputed"):
        return None
    ta = _single_value_template(a.text)
    tb = _single_value_template(b.text)
    if not ta or not tb:
        return None
    template_a, value_a = ta
    template_b, value_b = tb
    if template_a != template_b or value_a == value_b:
        return None

    da, db_doc = _doc(db, a), _doc(db, b)
    if da and db_doc and da.family_id and da.family_id == db_doc.family_id:
        newer, older = (a, b) if _rank(da) >= _rank(db_doc) else (b, a)
        newer_doc, older_doc = (da, db_doc) if newer is a else (db_doc, da)
        if _rank(newer_doc) > _rank(older_doc):
            older.status = "superseded"
            older.valid_to = newer.valid_from or datetime.utcnow()
            newer.status = "active"
            newer.supersedes_claim_id = older.id
            return _create(
                db, newer, older, "version_update", "high", True,
                f"Superseded by newer revision {newer_doc.revision or newer_doc.published_at}",
            )
    # Different sources / same revision / unknown lineage → human.
    a.status = "disputed"
    b.status = "disputed"
    return _create(db, a, b, "source_conflict", "high", False)


def scan_conflicts(db: Session, topic: Optional[str] = None) -> dict:
    query = db.query(CanonicalClaim).filter(
        CanonicalClaim.status.in_(["active", "disputed"]),
        CanonicalClaim.value_normalized.isnot(None),
    )
    if topic:
        query = query.filter(CanonicalClaim.topic == topic)
    claims = query.all()
    groups: dict[tuple[str, str], list[CanonicalClaim]] = {}
    for c in claims:
        groups.setdefault((c.topic, c.actor), []).append(c)
    created = 0
    compared = 0
    affected = set()
    affected_claims = set()
    for group in groups.values():
        group = group[:MAX_GROUP]
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                compared += 1
                row = _compare(db, group[i], group[j])
                if row is not None:
                    created += 1
                    affected.update([group[i].topic, group[j].topic])
                    affected_claims.update([group[i].id, group[j].id])
        db.commit()
    if affected_claims:
        try:
            from softwiki.knowledge.projections import reproject_claims
            reproject_claims(db, affected_claims)
        except Exception:
            pass
    if affected:
        try:
            from softwiki.knowledge.wiki_queue import enqueue_wiki_rebuild
            enqueue_wiki_rebuild(db, affected, reason="conflict_scan")
        except Exception:
            pass
    return {"canonical_claims": len(claims), "pairs": compared, "created": created}


def list_conflicts(db: Session, status: Optional[str] = None) -> list[dict]:
    query = db.query(Contradiction).order_by(Contradiction.created_at.desc())
    if status:
        query = query.filter(Contradiction.status == status)
    rows = query.all()
    out = []
    for row in rows:
        a = db.query(CanonicalClaim).filter(CanonicalClaim.id == row.claim_a_id).first()
        b = db.query(CanonicalClaim).filter(CanonicalClaim.id == row.claim_b_id).first()
        da = _doc(db, a) if a else None
        db_doc = _doc(db, b) if b else None
        out.append({
            "id": row.id,
            "type": row.type,
            "severity": row.severity,
            "status": row.status,
            "auto_resolved": bool(row.auto_resolved),
            "resolution": row.resolution,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "claim_a": _claim_payload(a, da),
            "claim_b": _claim_payload(b, db_doc),
        })
    return out


def _claim_payload(c: Optional[CanonicalClaim], doc: Optional[Document]) -> Optional[dict]:
    if c is None:
        return None
    return {
        "id": c.id,
        "text": c.text,
        "actor": c.actor,
        "topic": c.topic,
        "stance": c.stance,
        "status": c.status,
        "confidence": c.confidence,
        "value_normalized": c.value_normalized,
        "document_id": c.primary_document_id,
        "title": doc.title if doc else None,
        "source_name": doc.source_name if doc else None,
        "published_at": doc.published_at.isoformat() if doc and doc.published_at else None,
        "revision": doc.revision if doc else None,
        "page_start": c.primary_page_start,
        "page_end": c.primary_page_end,
    }


def adjudicate(db: Session, contradiction_id: int, action: str,
               actor: str = "wiki-admin", reason: str = "") -> dict:
    row = db.query(Contradiction).filter(Contradiction.id == contradiction_id).first()
    if row is None:
        raise ValueError("Contradiction not found")
    a = db.query(CanonicalClaim).filter(CanonicalClaim.id == row.claim_a_id).first()
    b = db.query(CanonicalClaim).filter(CanonicalClaim.id == row.claim_b_id).first()
    if not a or not b:
        raise ValueError("Contradiction references a missing claim")
    before = {
        "status": row.status,
        "a_status": a.status,
        "b_status": b.status,
        "resolution": row.resolution,
    }
    if action == "accept_a":
        a.status, b.status = "active", "superseded"
        b.valid_to = datetime.utcnow()
        row.status, row.resolution = "resolved", reason or "Accepted claim A"
    elif action == "accept_b":
        a.status, b.status = "superseded", "active"
        a.valid_to = datetime.utcnow()
        row.status, row.resolution = "resolved", reason or "Accepted claim B"
    elif action == "keep_both":
        a.status = b.status = "active"
        row.status, row.resolution = "resolved", reason or "Kept both (scope/revision differs)"
    elif action == "mark_error_a":
        a.status, b.status = "retracted", "active"
        row.status, row.resolution = "resolved", reason or "Claim A marked extraction error"
    elif action == "mark_error_b":
        a.status, b.status = "active", "retracted"
        row.status, row.resolution = "resolved", reason or "Claim B marked extraction error"
    elif action == "needs_evidence":
        a.status = b.status = "disputed"
        row.status, row.resolution = "needs_evidence", reason or "More evidence required"
    elif action == "reopen":
        a.status = b.status = "disputed"
        row.status, row.resolution = "open", reason or "Reopened"
    else:
        raise ValueError(f"Unsupported action: {action}")
    row.resolved_by = actor
    row.resolved_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    after = {
        "status": row.status,
        "a_status": a.status,
        "b_status": b.status,
        "resolution": row.resolution,
    }
    db.add(Adjudication(
        contradiction_id=row.id,
        action=action,
        before_json=json.dumps(before, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False),
        actor=actor,
        reason=reason or None,
    ))
    try:
        from softwiki.knowledge.projections import reproject_claims
        reproject_claims(db, [a.id, b.id])
    except Exception:
        pass
    mark_wiki_stale_for_topics(db, [a.topic, b.topic], reason=f"adjudication:{action}")
    try:
        from softwiki.knowledge.wiki_queue import enqueue_wiki_rebuild
        enqueue_wiki_rebuild(db, [a.topic, b.topic], reason=f"adjudication:{action}")
    except Exception:
        pass
    db.commit()
    return {"id": row.id, "status": row.status, "claim_a": a.status, "claim_b": b.status}


def _rebuild_counts(db: Session) -> dict:
    from softwiki.source_store.models import WikiRebuildTask
    return {
        "pending": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "pending").count(),
        "running": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "running").count(),
        "failed": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "failed").count(),
        "done": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "done").count(),
    }


def metrics(db: Session) -> dict:
    from sqlalchemy import func
    from softwiki.source_store.models import Claim, Event, Relationship
    canonical = {
        status: count for status, count in
        db.query(CanonicalClaim.status, func.count(CanonicalClaim.id)).group_by(CanonicalClaim.status).all()
    }
    contradictions = {
        status: count for status, count in
        db.query(Contradiction.status, func.count(Contradiction.id)).group_by(Contradiction.status).all()
    }
    by_type = {
        ctype: count for ctype, count in
        db.query(Contradiction.type, func.count(Contradiction.id)).group_by(Contradiction.type).all()
    }
    return {
        "raw_claims": db.query(func.count(Claim.id)).scalar() or 0,
        "canonical_claims": db.query(func.count(CanonicalClaim.id)).scalar() or 0,
        "evidence": db.query(func.count(ClaimEvidence.id)).scalar() or 0,
        "canonical_status": canonical,
        "contradictions": contradictions,
        "contradictions_by_type": by_type,
        "stale_wiki_artifacts": db.query(func.count(WikiArtifactState.id)).filter(
            WikiArtifactState.stale_at.isnot(None)
        ).scalar() or 0,
        "relationships": db.query(func.count(Relationship.id)).scalar() or 0,
        "relationships_linked": db.query(func.count(Relationship.id)).filter(
            Relationship.canonical_claim_id.isnot(None)
        ).scalar() or 0,
        "events": db.query(func.count(Event.id)).scalar() or 0,
        "events_linked": db.query(func.count(Event.id)).filter(
            Event.canonical_claim_id.isnot(None)
        ).scalar() or 0,
        "wiki_rebuild_tasks": _rebuild_counts(db),
    }
