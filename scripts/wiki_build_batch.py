"""Batch-generate subject wiki pages for one knowledge base.

Picks subjects from /api/wiki/pages?refresh=true and builds them, in parallel.
Each subject is one LLM job; concurrency is what makes a 400-subject corpus
finish in tens of minutes instead of many hours.

Subjects marked ignore in config/wiki_subjects.yaml are already absent from the
candidate list; locked ones are skipped by the server.

Usage:
    python3 scripts/wiki_build_batch.py http://127.0.0.1:6200 [limit] [skip_over] [workers]
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def _get(url: str, timeout: int = 300) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def _post(url: str, payload: dict, timeout: int = 900) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:6200").rstrip("/")
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    skip_split_over = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 4

    listing = _get(f"{base}/api/wiki/pages?refresh=true", timeout=300)
    candidates = listing.get("candidates") or []
    if not candidates:
        print("no candidates returned")
        return 1

    already = {s.get("subject") for s in (listing.get("subjects") or [])}
    todo = [c for c in candidates if c["subject"] not in already]
    if skip_split_over:
        todo = [c for c in todo if c["claims_total"] <= skip_split_over]
    todo = todo[:limit]

    print(f"{len(candidates)} candidates, {len(todo)} to build, {workers} workers", flush=True)

    lock = threading.Lock()
    stats = {"ok": 0, "failed": 0}
    started = time.time()

    def build(cand: dict) -> None:
        t0 = time.time()
        try:
            res = _post(f"{base}/api/wiki/pages/build", {"subject": cand["subject"]})
            pages = res.get("pages") or []
            with lock:
                stats["ok"] += 1
                done = stats["ok"] + stats["failed"]
            print(
                f"[{done}/{len(todo)}] OK   {cand['subject'][:28]:28} "
                f"claims={res.get('claims_total'):>4} pages={len(pages)} "
                f"{time.time() - t0:.1f}s",
                flush=True,
            )
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:160]
            with lock:
                stats["failed"] += 1
                done = stats["ok"] + stats["failed"]
            print(f"[{done}/{len(todo)}] FAIL {cand['subject'][:28]:28} HTTP {e.code} {body}",
                  flush=True)
        except Exception as e:  # noqa: BLE001 - report and continue
            with lock:
                stats["failed"] += 1
                done = stats["ok"] + stats["failed"]
            print(f"[{done}/{len(todo)}] FAIL {cand['subject'][:28]:28} {e}", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(build, c) for c in todo]
        for _ in as_completed(futures):
            pass

    elapsed = time.time() - started
    print(f"\ndone: {stats['ok']} ok, {stats['failed']} failed in {elapsed / 60:.1f} min")
    return 0 if stats["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
