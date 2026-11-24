#!/usr/bin/env python3
"""Parallel re-extraction for a whole knowledge base.

Phase 1 — extraction (parallel): each worker owns one document, uses its own
session, deletes that document's old claims/relationships/events and re-runs the
pipeline with the current prompts. Canonicalization is skipped here on purpose.

Phase 2 — canonicalization (serial): canonical claim ids are global, so this
runs on one thread to avoid unique-key races.

Phase 3 — prune: canonical claims that no longer have any evidence row.

Phase 4 — optional graph normalization (``--normalize``).

Usage:
    python scripts/graph_reextract.py --workers 6 --windows 6 --normalize
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.extraction.processor import run_extraction_pipeline
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import (
    CanonicalClaim,
    Claim,
    ClaimEvidence,
    Document,
    Event,
    Relationship,
)


def _extract_one(doc_id: int, windows: int) -> dict:
    os.environ["EXTRACTION_MAX_WINDOWS"] = str(windows)
    os.environ["EXTRACTION_SKIP_CANONICALIZE"] = "1"
    db = SessionLocal()
    started = time.time()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc is None:
            return {"doc": doc_id, "error": "not found"}
        db.query(Claim).filter(Claim.document_id == doc_id).delete()
        db.query(Relationship).filter(Relationship.document_id == doc_id).delete()
        db.query(Event).filter(Event.document_id == doc_id).delete()
        db.commit()
        result = run_extraction_pipeline(
            db, doc.id, doc.cleaned_text, doc.published_at, background=False
        )
        return {"doc": doc_id, "seconds": round(time.time() - started, 1), **result}
    except Exception as exc:  # noqa: BLE001 - keep other workers alive
        db.rollback()
        return {"doc": doc_id, "error": str(exc)}
    finally:
        db.close()


def _canonicalize_one(doc_id: int) -> dict:
    from softwiki.knowledge.canonical import canonicalize_document

    db = SessionLocal()
    try:
        stats = canonicalize_document(db, doc_id)
        db.commit()
        return {"doc": doc_id, "canonical": stats}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"doc": doc_id, "error": str(exc)}
    finally:
        db.close()


def _prune_canonical(db) -> int:
    used = db.query(ClaimEvidence.canonical_id).filter(
        ClaimEvidence.canonical_id.isnot(None)
    ).distinct()
    used_ids = {row[0] for row in used}
    orphans = [
        row.id for row in db.query(CanonicalClaim.id).all()
        if row[0] not in used_ids
    ]
    if orphans:
        db.query(CanonicalClaim).filter(CanonicalClaim.id.in_(orphans)).delete(
            synchronize_session=False
        )
        db.commit()
    return len(orphans)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--windows", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--doc-id", type=int, default=None)
    parser.add_argument("--normalize", action="store_true")
    args = parser.parse_args()

    init_tables()
    db = SessionLocal()
    try:
        query = db.query(Document.id).order_by(Document.id)
        if args.doc_id:
            query = query.filter(Document.id == args.doc_id)
        if args.limit:
            query = query.limit(args.limit)
        doc_ids = [row[0] for row in query.all()]
    finally:
        db.close()

    print(json.dumps({"phase": "extract", "documents": len(doc_ids),
                      "workers": args.workers, "windows": args.windows}), flush=True)
    failures = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_extract_one, doc_id, args.windows) for doc_id in doc_ids]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result.get("error"):
                failures.append(result)
            print(f"[{index}/{len(doc_ids)}] {json.dumps(result, ensure_ascii=False)}", flush=True)
    print(json.dumps({"phase": "extract_done", "seconds": round(time.time() - started, 1),
                      "failures": len(failures)}), flush=True)

    print(json.dumps({"phase": "canonicalize", "documents": len(doc_ids)}), flush=True)
    canonical_failures = []
    for index, doc_id in enumerate(doc_ids, 1):
        result = _canonicalize_one(doc_id)
        if result.get("error"):
            canonical_failures.append(result)
        if index % 10 == 0 or index == len(doc_ids):
            print(f"[{index}/{len(doc_ids)}] canonicalized", flush=True)

    db = SessionLocal()
    try:
        pruned = _prune_canonical(db)
    finally:
        db.close()
    print(json.dumps({"phase": "pruned", "canonical_claims": pruned}), flush=True)

    if args.normalize:
        from scripts.graph_normalize import normalize
        db = SessionLocal()
        try:
            print(json.dumps({"phase": "normalize", **normalize(db)}, ensure_ascii=False), flush=True)
        finally:
            db.close()

    print(json.dumps({"phase": "done", "extract_failures": failures,
                      "canonical_failures": canonical_failures}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
