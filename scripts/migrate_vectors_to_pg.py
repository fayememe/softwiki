#!/usr/bin/env python3
"""Migrate the legacy .npz vector index into PostgreSQL + pgvector.

The npz file is keyed by chunk id, so no re-embedding is needed:

1. ensure the ``vector`` extension and ``chunk_embeddings`` table exist;
2. drop vectors whose chunk no longer exists (the file accumulates orphans);
3. batch-upsert live vectors (float32, cosine);
4. build an HNSW index;
5. verify counts and compare file-vs-pg top-k recall on sample queries.

Usage:
    python scripts/migrate_vectors_to_pg.py [--npz PATH] [--batch 200]
        [--index hnsw|ivfflat|none] [--samples 20] [--json /tmp/report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.config import get_index_path
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Chunk


def _ensure_schema(store) -> None:
    db = SessionLocal()
    try:
        store._ensure_schema(db)
    finally:
        db.close()


def _create_index(store, kind: str) -> None:
    if kind == "none":
        return
    from sqlalchemy import text
    db = SessionLocal()
    try:
        if kind == "ivfflat":
            lists = max(10, min(2000, int(os.getenv("PGVECTOR_IVFFLAT_LISTS", "100"))))
            db.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_ivfflat "
                f"ON chunk_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists={lists})"
            ))
            db.execute(text("ANALYZE chunk_embeddings"))
        else:
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_hnsw "
                "ON chunk_embeddings USING hnsw (embedding vector_cosine_ops) "
                "WITH (m=16, ef_construction=64)"
            ))
        db.commit()
    finally:
        db.close()


def _recall(store, ids: list[int], matrix: np.ndarray,
            samples: int, top_k: int = 50) -> dict:
    """Compare file (float64 brute force) vs pgvector top-k for sample rows."""
    rng = np.random.default_rng(7)
    picks = rng.choice(len(ids), size=min(samples, len(ids)), replace=False)
    matrix32 = matrix.astype(np.float32)
    norms = np.linalg.norm(matrix32, axis=1)
    norms[norms == 0] = 1e-10
    overlaps = []
    latencies = []
    for pick in picks:
        query = matrix32[pick]
        # file backend result (float32 for a fair index comparison)
        started = time.perf_counter()
        sims = matrix32 @ query / (norms * (np.linalg.norm(query) or 1e-10))
        file_top = [ids[i] for i in np.argsort(sims)[::-1][:top_k]]
        # pgvector result
        t0 = time.perf_counter()
        pg_rows = store.search(query.tolist(), top_k=top_k)
        latencies.append((time.perf_counter() - t0) * 1000)
        pg_top = [row["chunk_id"] for row in pg_rows]
        overlap = len(set(file_top) & set(pg_top)) / float(top_k)
        overlaps.append(overlap)
    return {
        "samples": len(overlaps),
        "mean_recall_at_k": round(float(np.mean(overlaps)), 4) if overlaps else 0.0,
        "min_recall_at_k": round(float(np.min(overlaps)), 4) if overlaps else 0.0,
        "pg_latency_p50_ms": round(float(np.median(latencies)), 2) if latencies else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--npz", default=None)
    parser.add_argument("--batch", type=int, default=200)
    parser.add_argument("--index", choices=["hnsw", "ivfflat", "none"], default="hnsw")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--json", default=None)
    parser.add_argument("--skip-recall", action="store_true")
    args = parser.parse_args()

    npz_path = args.npz or get_index_path("vector_index.npz")
    if not os.path.exists(npz_path):
        raise SystemExit(f"npz not found: {npz_path}")

    init_tables()
    os.environ["SOFTWIKI_VECTOR_BACKEND"] = "pg"
    from softwiki.rag.vector_store import PgVectorStore

    store = PgVectorStore()
    _ensure_schema(store)

    started = time.perf_counter()
    data = np.load(npz_path, allow_pickle=True)
    ids = [int(cid) for cid in data["chunk_ids"]]
    matrix = np.asarray(data["embeddings"])
    del data
    load_seconds = round(time.perf_counter() - started, 1)
    print(json.dumps({"phase": "loaded", "vectors": len(ids), "shape": list(matrix.shape),
                      "dtype": str(matrix.dtype), "seconds": load_seconds}), flush=True)

    db = SessionLocal()
    try:
        live = {row[0] for row in db.query(Chunk.id).all()}
    finally:
        db.close()
    keep = [(cid, idx) for idx, cid in enumerate(ids) if cid in live]
    dropped = len(ids) - len(keep)
    print(json.dumps({"phase": "filtered", "live_chunks": len(live),
                      "keep": len(keep), "orphans_dropped": dropped}), flush=True)

    started = time.perf_counter()
    inserted = 0
    for offset in range(0, len(keep), max(1, args.batch)):
        batch = keep[offset:offset + max(1, args.batch)]
        batch_ids = [cid for cid, _ in batch]
        batch_vectors = [matrix[idx].tolist() for _, idx in batch]
        store.add_vectors(batch_ids, batch_vectors)
        inserted += len(batch)
        if inserted % (args.batch * 10) < args.batch:
            print(json.dumps({"phase": "insert", "done": inserted, "total": len(keep)}), flush=True)
    insert_seconds = round(time.perf_counter() - started, 1)

    _create_index(store, args.index)
    index_seconds = round(time.perf_counter() - started - insert_seconds, 1)

    report = {
        "phase": "done",
        "npz": npz_path,
        "inserted": inserted,
        "orphans_dropped": dropped,
        "insert_seconds": insert_seconds,
        "index": args.index,
        "index_seconds": index_seconds,
        "dim": int(matrix.shape[1]) if matrix.ndim == 2 else None,
    }
    if not args.skip_recall:
        live_ids = [cid for cid, _ in keep]
        live_matrix = matrix[[idx for _, idx in keep]]
        report["recall"] = _recall(store, live_ids, live_matrix, args.samples)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
