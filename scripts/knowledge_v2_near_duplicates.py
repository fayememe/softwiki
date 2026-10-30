#!/usr/bin/env python3
"""P2 v0 near-duplicate document report.

Bottom-k MinHash over word 5-shingles. This is a report, not an automatic
merge: exact hash/URL duplicates are already handled at ingest.
"""
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Document

K = 128
TOKEN_RE = re.compile(r"[a-z0-9_]+")


def signature(text: str) -> set[int]:
    tokens = TOKEN_RE.findall((text or "").lower())
    shingles = {
        hashlib.blake2b(" ".join(tokens[i:i + 5]).encode("utf-8"), digest_size=8).digest()
        for i in range(max(0, len(tokens) - 4))
    }
    return set(sorted(shingles)[:K])


def main():
    init_tables()
    db = SessionLocal()
    try:
        docs = db.query(Document).all()
        sigs = [(d.id, d.title, d.source_name, signature(d.cleaned_text or d.raw_text)) for d in docs]
        pairs = []
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                a, b = sigs[i][3], sigs[j][3]
                if not a or not b:
                    continue
                score = len(a & b) / max(1, min(len(a), len(b)))
                if score >= 0.5:
                    pairs.append((round(score, 3), sigs[i][0], sigs[j][0], sigs[i][1], sigs[j][1]))
        pairs.sort(reverse=True)
        print({"documents": len(docs), "candidate_pairs": len(pairs)}, flush=True)
        for p in pairs[:50]:
            print(p, flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
