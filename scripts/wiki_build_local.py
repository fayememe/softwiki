#!/usr/bin/env python3
"""Generate wiki subject pages directly (no HTTP), for a standalone container.

CI deploys restart the api container; a batch that talks to the API dies with
it. This runner is designed to live in its own container (not managed by
compose), so deploys do not interrupt it.

It enumerates subject candidates, skips subjects that already have pages, and
generates in parallel with one session per worker. Failures are retried once.

Usage:
    python scripts/wiki_build_local.py [--limit 500] [--workers 3]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.wiki.subject_pages import (
    generate_subject_pages,
    list_generated_pages,
    subject_candidates,
)

PRINT_LOCK = threading.Lock()


def _log(message: str) -> None:
    with PRINT_LOCK:
        print(message, flush=True)


def _build_one(subject: str, total: int) -> dict:
    started = time.time()
    last_error = ""
    for attempt in (1, 2):
        db = SessionLocal()
        try:
            result = generate_subject_pages(db, subject)
            db.commit()
            return {
                "subject": subject, "status": "ok",
                "pages": len(result.get("pages") or []),
                "claims": result.get("claims_total"),
                "seconds": round(time.time() - started, 1),
                "attempt": attempt,
            }
        except Exception as exc:  # noqa: BLE001 - retry then report
            db.rollback()
            last_error = str(exc)
            if attempt == 1:
                time.sleep(5)
        finally:
            db.close()
    return {"subject": subject, "status": "failed", "error": last_error[:300],
            "seconds": round(time.time() - started, 1)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--min-relations", type=int, default=None)
    args = parser.parse_args()

    init_tables()
    db = SessionLocal()
    try:
        kwargs = {}
        if args.min_relations:
            kwargs["min_relations"] = args.min_relations
        candidates = subject_candidates(db, use_cache=False, **kwargs)
        have = {s.get("subject") for s in list_generated_pages(db).get("subjects", [])}
    finally:
        db.close()

    todo = [c["subject"] for c in candidates if c["subject"] not in have][: args.limit]
    _log(json.dumps({"phase": "start", "candidates": len(candidates),
                     "already": len(have), "todo": len(todo),
                     "workers": args.workers}, ensure_ascii=False))

    stats = {"ok": 0, "failed": 0}
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(_build_one, subject, len(todo)): subject for subject in todo}
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            stats[result["status"]] = stats.get(result["status"], 0) + 1
            _log(f"[{index}/{len(todo)}] {json.dumps(result, ensure_ascii=False)}")

    _log("done: " + json.dumps({
        **stats, "seconds": round(time.time() - started, 1),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
