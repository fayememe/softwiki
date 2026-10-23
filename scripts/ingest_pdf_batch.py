#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
from pathlib import Path

import requests


def pending_count(db_path):
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "select count(*) from documents where status in ('pending','extracting')"
        ).fetchone()
    return int(row[0]) if row else 0


def wait_for_extraction(db_path, timeout, interval=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pending_count(db_path) == 0:
            return True
        time.sleep(interval)
    return False


def upload(api, path, timeout):
    with path.open("rb") as fh:
        resp = requests.post(
            api.rstrip("/") + "/api/ingest/file",
            files={"file": (path.name, fh, "application/pdf")},
            timeout=timeout,
        )
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": resp.text[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--api", default="http://127.0.0.1:6200")
    ap.add_argument("--db", required=True)
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--upload-timeout", type=int, default=1800)
    ap.add_argument("--extract-timeout", type=int, default=1800)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--index", action="store_true")
    args = ap.parse_args()

    files = sorted(Path(args.dir).rglob("*.pdf"))
    if args.limit:
        files = files[:args.limit]
    print(f"files={len(files)} batch={args.batch_size}", flush=True)

    counts = {"success": 0, "skipped": 0, "failed": 0}
    for i, path in enumerate(files, 1):
        try:
            code, body = upload(args.api, path, args.upload_timeout)
            status = body.get("status", f"http_{code}")
            key = status if status in counts else "failed"
            counts[key] += 1
            print(
                f"[{i}/{len(files)}] {path.parent.name}/{path.name} -> "
                f"{code} {status} {body.get('reason', '')}",
                flush=True,
            )
        except Exception as exc:
            counts["failed"] += 1
            print(f"[{i}/{len(files)}] {path} -> exception {exc}", flush=True)

        if i % args.batch_size == 0 or i == len(files):
            settled = wait_for_extraction(args.db, args.extract_timeout)
            print(
                f"  extraction pending={pending_count(args.db)} settled={settled}",
                flush=True,
            )

    print(f"summary={json.dumps(counts)}", flush=True)

    if args.index:
        print("calling /api/index ...", flush=True)
        resp = requests.post(args.api.rstrip("/") + "/api/index", timeout=7200)
        print(f"index={resp.status_code} {resp.text[:300]}", flush=True)


if __name__ == "__main__":
    main()
