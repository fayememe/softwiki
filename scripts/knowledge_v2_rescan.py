#!/usr/bin/env python3
"""Reset v0 auto-generated source-conflict candidates and rescan conservatively.

Only for the initial v0 migration; no human adjudications are expected yet.
Run inside the API container.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Adjudication, CanonicalClaim, Contradiction
from softwiki.knowledge.conflicts import scan_conflicts, metrics
from softwiki.knowledge.canonical import mark_wiki_stale_for_topics


def main():
    init_tables()
    db = SessionLocal()
    try:
        rows = db.query(Contradiction).filter(
            Contradiction.type == "source_conflict",
            Contradiction.auto_resolved.is_(False),
        ).all()
        ids = [r.id for r in rows]
        if ids:
            db.query(Adjudication).filter(Adjudication.contradiction_id.in_(ids)).delete(
                synchronize_session=False
            )
            db.query(Contradiction).filter(Contradiction.id.in_(ids)).delete(
                synchronize_session=False
            )
        disputed = db.query(CanonicalClaim).filter(CanonicalClaim.status == "disputed").all()
        for c in disputed:
            c.status = "active"
        db.commit()
        print({"removed_source_conflicts": len(ids), "reactivated_claims": len(disputed)})
        print(scan_conflicts(db))
        print(metrics(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
