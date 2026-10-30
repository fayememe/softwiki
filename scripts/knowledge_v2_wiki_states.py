#!/usr/bin/env python3
"""Mark pre-canonical wiki pages stale and record their artifact state."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.knowledge.canonical import backfill_wiki_states
from softwiki.knowledge.conflicts import metrics


def main():
    init_tables()
    db = SessionLocal()
    try:
        print(backfill_wiki_states(db, mark_stale=True))
        print(metrics(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
