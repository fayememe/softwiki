"""Document family/revision assignment (v0, deterministic)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from softwiki.source_store.models import Document


def _normalize_title(title: str) -> str:
    text = (title or "").lower()
    text = re.sub(r"\b(issue|revision|rev|r\d+p\d+)\b.*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ._-")
    return text


def family_id_for(doc: Document) -> str:
    if doc.url:
        parsed = urlparse(doc.url)
        path = (parsed.netloc + parsed.path).lower().rstrip("/")
        return f"url:{path}"
    source = (doc.source_name or "unknown").lower().strip()
    title = _normalize_title(doc.title)
    return f"doc:{source}|{title}"


def revision_for(doc: Document) -> str:
    if doc.revision:
        return str(doc.revision)
    when = doc.published_at or doc.collected_at
    return when.isoformat() if isinstance(when, datetime) else "unknown"


def _rank(doc: Document) -> tuple:
    when = doc.published_at or doc.collected_at
    return (when or datetime.min, doc.id or 0)


def assign_document_version(db: Session, doc: Document) -> Document:
    """Fill family/revision and link supersedes for a new document."""
    if not doc.family_id:
        doc.family_id = family_id_for(doc)
    if not doc.revision:
        doc.revision = revision_for(doc)
    # Flush family/revision so the previous-document query sees them even when
    # the caller has not committed yet.
    db.flush()
    previous = (
        db.query(Document)
        .filter(Document.family_id == doc.family_id, Document.id != doc.id)
        .all()
    )
    if previous:
        newer = max(previous + [doc], key=_rank)
        if newer.id == doc.id:
            prior = max(previous, key=_rank)
            if _rank(prior) < _rank(doc):
                doc.supersedes_document_id = prior.id
    return doc


def backfill_document_versions(db: Session) -> dict:
    docs = db.query(Document).all()
    changed = 0
    for doc in docs:
        before = (doc.family_id, doc.revision, doc.supersedes_document_id)
        assign_document_version(db, doc)
        if (doc.family_id, doc.revision, doc.supersedes_document_id) != before:
            changed += 1
    db.commit()
    return {"documents": len(docs), "changed": changed}
