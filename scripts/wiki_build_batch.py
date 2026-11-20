"""Batch-generate subject wiki pages for one knowledge base.

Picks the top-N subjects by graph degree from /api/wiki/pages?refresh=true and
builds each one sequentially, so a large library can be filled in without
hammering the LLM. Progress is appended to stdout; failures are reported but do
not abort the run.

Usage (on the host, against the running API):
    python3 scripts/wiki_build_batch.py http://127.0.0.1:6200 40
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


def _get(url: str, timeout: int = 180) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def _post(url: str, payload: dict, timeout: int = 600) -> dict:
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

    listing = _get(f"{base}/api/wiki/pages?refresh=true", timeout=300)
    candidates = listing.get("candidates") or []
    if not candidates:
        print("no candidates returned")
        return 1

    already = {s.get("slug") for s in (listing.get("subjects") or [])}
    todo = [c for c in candidates if c["slug"] not in already]
    if skip_split_over:
        todo = [c for c in todo if c["claims_total"] <= skip_split_over]
    todo = todo[:limit]

    print(f"{len(candidates)} candidates, {len(todo)} to build", flush=True)
    ok = failed = 0
    started = time.time()

    for i, c in enumerate(todo, 1):
        t0 = time.time()
        try:
            res = _post(f"{base}/api/wiki/pages/build", {"subject": c["subject"]})
            pages = res.get("pages") or []
            ok += 1
            print(
                f"[{i}/{len(todo)}] OK   {c['subject'][:28]:28} "
                f"claims={res.get('claims_total'):>4} pages={len(pages)} "
                f"{time.time() - t0:.1f}s",
                flush=True,
            )
        except urllib.error.HTTPError as e:
            failed += 1
            body = e.read().decode()[:160]
            print(f"[{i}/{len(todo)}] FAIL {c['subject'][:28]:28} HTTP {e.code} {body}", flush=True)
        except Exception as e:  # noqa: BLE001 - report and continue
            failed += 1
            print(f"[{i}/{len(todo)}] FAIL {c['subject'][:28]:28} {e}", flush=True)

    elapsed = time.time() - started
    print(f"\ndone: {ok} ok, {failed} failed in {elapsed / 60:.1f} min")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
