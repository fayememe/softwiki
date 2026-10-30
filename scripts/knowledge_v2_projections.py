#!/usr/bin/env python3
"""Heuristic v0 backfill: attach relationship/event rows to canonical claims."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import CanonicalClaim, Event, Relationship
from softwiki.knowledge.canonical import jaccard


def _best(claims, text):
    best = None
    best_score = 0.0
    for c in claims:
        score = jaccard(text, c.text)
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 0.12 else None


def main():
    init_tables()
    db = SessionLocal()
    try:
        cache = {}
        rels = db.query(Relationship).filter(Relationship.canonical_claim_id.is_(None)).all()
        rel_linked = 0
        for rel in rels:
            if rel.document_id not in cache:
                cache[rel.document_id] = db.query(CanonicalClaim).filter(
                    CanonicalClaim.primary_document_id == rel.document_id,
                    CanonicalClaim.status.in_(["active", "disputed"]),
                ).all()
            claim = _best(cache[rel.document_id], f"{rel.source_name} {rel.target_name} {rel.description or ''}")
            if claim:
                rel.canonical_claim_id = claim.id
                rel.status = claim.status
                rel_linked += 1
        db.commit()

        events = db.query(Event).filter(Event.canonical_claim_id.is_(None)).all()
        event_linked = 0
        for ev in events:
            if ev.document_id not in cache:
                cache[ev.document_id] = db.query(CanonicalClaim).filter(
                    CanonicalClaim.primary_document_id == ev.document_id,
                    CanonicalClaim.status.in_(["active", "disputed"]),
                ).all()
            claim = _best(cache[ev.document_id], f"{ev.title} {ev.description or ''}")
            if claim:
                ev.canonical_claim_id = claim.id
                ev.status = claim.status
                event_linked += 1
        db.commit()
        print({"relationships": len(rels), "linked": rel_linked,
               "events": len(events), "event_linked": event_linked})
    finally:
        db.close()


if __name__ == "__main__":
    main()
