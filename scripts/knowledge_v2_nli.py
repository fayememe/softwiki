#!/usr/bin/env python3
"""NLI/LLM conflict judge v0 (candidate generation + cached verdicts)."""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.knowledge.nli import judge_candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    init_tables()
    db = SessionLocal()
    try:
        result = judge_candidates(db, limit=args.limit, apply=args.apply)
        for row in result.get("results", []):
            print(row, flush=True)
        print({k: result[k] for k in result if k != "results"}, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
