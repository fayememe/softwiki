#!/usr/bin/env python3
"""Rebuild stale WikiArtifact pages one by one (v0 queue)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import WikiArtifactState
from softwiki.wiki.page_generator import WikiPageGenerator


def main():
    init_tables()
    db = SessionLocal()
    gen = WikiPageGenerator()
    try:
        rows = db.query(WikiArtifactState).filter(
            WikiArtifactState.stale_at.isnot(None)
        ).order_by(WikiArtifactState.stale_at.asc()).all()
        print({"stale": len(rows)}, flush=True)
        ok = fail = 0
        for state in rows:
            try:
                print(f"[wiki] rebuilding {state.topic}", flush=True)
                gen.generate_topic_page(db, state.topic, force_rebuild=True)
                ok += 1
            except Exception as exc:
                fail += 1
                print(f"[wiki] failed {state.topic}: {exc}", flush=True)
        print({"ok": ok, "failed": fail, "stale_remaining": db.query(WikiArtifactState).filter(WikiArtifactState.stale_at.isnot(None)).count()}, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
