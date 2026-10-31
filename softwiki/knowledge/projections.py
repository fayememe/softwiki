"""Reproject canonical claim status changes into Graph/Timeline rows."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from softwiki.source_store.models import CanonicalClaim, Event, Relationship


def reproject_claims(db: Session, claim_ids: Iterable[str]) -> dict:
    ids = {c for c in claim_ids if c}
    if not ids:
        return {"claims": 0, "relationships": 0, "events": 0}
    claims = {
        c.id: c for c in db.query(CanonicalClaim).filter(CanonicalClaim.id.in_(ids)).all()
    }
    rel_count = 0
    ev_count = 0
    for rel in db.query(Relationship).filter(Relationship.canonical_claim_id.in_(ids)).all():
        claim = claims.get(rel.canonical_claim_id)
        if claim is None:
            continue
        rel.status = claim.status
        if claim.status in ("superseded", "retracted"):
            rel.valid_to = claim.valid_to or datetime.utcnow()
        else:
            rel.valid_to = None
        rel_count += 1
    for ev in db.query(Event).filter(Event.canonical_claim_id.in_(ids)).all():
        claim = claims.get(ev.canonical_claim_id)
        if claim is None:
            continue
        ev.status = claim.status
        ev_count += 1
    db.commit()
    return {"claims": len(claims), "relationships": rel_count, "events": ev_count}
