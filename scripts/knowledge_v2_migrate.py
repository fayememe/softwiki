#!/usr/bin/env python3
"""Idempotent v0 migration/backfill for the claim-centric knowledge layer.

Run inside the API container (it has DB drivers and WORKSPACE_DIR):
  docker exec softwiki-api-1 python scripts/knowledge_v2_migrate.py

Safe to re-run:
- adds missing columns/tables
- backfills family/revision
- canonicalizes only claims with canonical_id IS NULL
- rescans conflicts (deduplicated by pair/type)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.knowledge.versioning import backfill_document_versions
from softwiki.knowledge.canonical import backfill_canonical_claims
from softwiki.knowledge.conflicts import scan_conflicts, metrics


def main():
    print("[v2] init tables/columns")
    init_tables()
    db = SessionLocal()
    try:
        print("[v2] document versions")
        print(backfill_document_versions(db))
        print("[v2] canonical claims + evidence")
        print(backfill_canonical_claims(db))
        print("[v2] conflict scan v0")
        print(scan_conflicts(db))
        print("[v2] metrics")
        print(metrics(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
