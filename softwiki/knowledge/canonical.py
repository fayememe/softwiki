"""Deterministic claim canonicalization, evidence links, and conflict v0.

This module is intentionally additive: raw claims stay in `claims`; a
CanonicalClaim aggregates them and ClaimEvidence keeps provenance.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from softwiki.source_store.models import (
    CanonicalClaim,
    Chunk,
    Claim,
    ClaimEvidence,
    Contradiction,
    Document,
    WikiArtifactState,
)

_WS_RE = re.compile(r"[\s\u00a0]+")
_TOKEN_RE = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]")
_HEX_RE = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)
_NUM_RE = re.compile(r"(?<![a-z0-9])\d+(?:\.\d+)?(?![a-z0-9])", re.IGNORECASE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = _WS_RE.sub(" ", text).strip()
    return text.strip(" .,;:!?()[]{}\"'")


def token_set(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalize_text(text)))


def jaccard(a: str, b: str) -> float:
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def extract_value(text: str) -> Optional[str]:
    values = [v.lower() for v in _HEX_RE.findall(text or "")]
    values += [v for v in _NUM_RE.findall(text or "") if v not in {"0", "1"}]
    if not values:
        return None
    return "|".join(sorted(set(values)))[:200]


def canonical_key(text: str, actor: str, topic: str, stance: str) -> str:
    base = "|".join([
        normalize_text(text),
        (actor or "").lower().strip(),
        (topic or "").lower().strip(),
        (stance or "").lower().strip(),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def canonical_id(key: str) -> str:
    return "cc_" + key[:24]


def _quote_hash(claim_id: str, quote: str) -> str:
    return hashlib.sha256(f"{claim_id}|{quote}".encode("utf-8")).hexdigest()


def _best_chunk(chunks: list[Chunk], claim_text: str) -> Optional[Chunk]:
    cleaned = normalize_text(claim_text)
    if not cleaned:
        return None
    # v0: exact substring is cheap and reliable; otherwise use the first
    # chunk as a coarse page fallback (never fabricate a page).
    for chunk in chunks:
        if cleaned in normalize_text(chunk.text):
            return chunk
    return None


def _add_evidence(db: Session, claim: Claim, canonical: CanonicalClaim,
                  doc: Optional[Document], chunks: Optional[list[Chunk]] = None) -> None:
    quote = (claim.text or "")[:1000]
    qhash = _quote_hash(claim.id, quote)
    if db.query(ClaimEvidence).filter(
        ClaimEvidence.claim_id == claim.id,
        ClaimEvidence.quote_hash == qhash,
    ).first():
        return
    chunk = _best_chunk(chunks or [], claim.text) if chunks else None
    if chunk is None and doc is not None and claim.document_id:
        chunk = (
            db.query(Chunk)
            .filter(Chunk.document_id == claim.document_id)
            .order_by(Chunk.chunk_index.asc())
            .first()
        )
    ev = ClaimEvidence(
        claim_id=claim.id,
        canonical_id=canonical.id,
        document_id=claim.document_id,
        page_start=getattr(chunk, "page_start", None),
        page_end=getattr(chunk, "page_end", None),
        char_start=getattr(chunk, "char_start", None),
        char_end=getattr(chunk, "char_end", None),
        quote=quote,
        quote_hash=qhash,
        source_name=getattr(doc, "source_name", None),
        source_revision=getattr(doc, "revision", None),
        trust_level=getattr(doc, "trust_level", None),
        published_at=claim.published_at,
    )
    db.add(ev)
    if canonical.primary_document_id is None:
        canonical.primary_document_id = claim.document_id
        canonical.primary_page_start = ev.page_start
        canonical.primary_page_end = ev.page_end
    canonical.evidence_count = (canonical.evidence_count or 0) + 1


def canonicalize_claim(db: Session, claim: Claim, doc: Optional[Document] = None,
                       chunks: Optional[list[Chunk]] = None,
                       commit: bool = True) -> CanonicalClaim:
    key = canonical_key(claim.text, claim.actor, claim.topic, claim.stance)
    cid = canonical_id(key)
    value = extract_value(claim.text)
    canonical = db.query(CanonicalClaim).filter(CanonicalClaim.canonical_key == key).first()
    if canonical is None:
        canonical = CanonicalClaim(
            id=cid,
            canonical_key=key,
            text=claim.text,
            actor=claim.actor,
            topic=claim.topic,
            stance=claim.stance,
            confidence=claim.confidence or 0.5,
            status="active",
            valid_from=claim.published_at,
            value_normalized=value,
        )
        db.add(canonical)
        db.flush()
    else:
        canonical.confidence = max(canonical.confidence or 0.0, claim.confidence or 0.0)
        canonical.updated_at = datetime.utcnow()
    claim.canonical_id = canonical.id
    claim.canonical_key = key
    claim.value_normalized = value
    # Raw claims are provenance records; the canonical claim is the query unit.
    claim.status = "merged"
    _add_evidence(db, claim, canonical, doc, chunks)
    if commit:
        db.commit()
    return canonical


def backfill_canonical_claims(db: Session, batch: int = 500) -> dict:
    total = 0
    created = 0
    current_doc_id = None
    doc = None
    chunks: list[Chunk] = []
    last_id = ""
    while True:
        claims = (
            db.query(Claim)
            .filter(Claim.canonical_id.is_(None), Claim.id > last_id)
            .order_by(Claim.id.asc())
            .limit(batch)
            .all()
        )
        if not claims:
            break
        for claim in claims:
            if claim.document_id != current_doc_id:
                current_doc_id = claim.document_id
                doc = db.query(Document).filter(Document.id == current_doc_id).first()
                chunks = (
                    db.query(Chunk)
                    .filter(Chunk.document_id == current_doc_id)
                    .order_by(Chunk.chunk_index.asc())
                    .all()
                )
            key = canonical_key(claim.text, claim.actor, claim.topic, claim.stance)
            before = db.query(CanonicalClaim).filter(
                CanonicalClaim.canonical_key == key
            ).first()
            canonicalize_claim(db, claim, doc, chunks, commit=False)
            if before is None:
                created += 1
            total += 1
        last_id = claims[-1].id
        db.commit()
        print(f"[canonical] {total} raw claims processed, {created} canonical created", flush=True)
    return {"claims": total, "canonical_created": created}

def mark_wiki_stale_for_topics(db: Session, topics: Iterable[str], reason: str = "claim_changed") -> int:
    count = 0
    for topic in {t for t in topics if t}:
        state = db.query(WikiArtifactState).filter(WikiArtifactState.topic == topic).first()
        if state is None:
            state = WikiArtifactState(topic=topic)
            db.add(state)
        state.stale_at = datetime.utcnow()
        count += 1
    if count:
        db.commit()
    return count


def canonicalize_document(db: Session, doc_id: int) -> dict:
    """Canonicalize all claims for a document and refresh conflict/stale state."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    claims = db.query(Claim).filter(Claim.document_id == doc_id).all()
    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == doc_id)
        .order_by(Chunk.chunk_index.asc())
        .all()
    )
    topics = set()
    for claim in claims:
        canonical = canonicalize_claim(db, claim, doc, chunks, commit=False)
        topics.add(canonical.topic)
    db.commit()
    if topics:
        mark_wiki_stale_for_topics(db, topics, reason="document_canonicalized")
        try:
            from softwiki.knowledge.conflicts import scan_conflicts
            for topic in topics:
                scan_conflicts(db, topic)
        except Exception:
            pass
    return {"document_id": doc_id, "claims": len(claims), "topics": sorted(topics)}
