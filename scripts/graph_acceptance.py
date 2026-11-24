#!/usr/bin/env python3
"""Graph acceptance + latency for a knowledge base.

Runs every golden question twice at the retrieval layer:

* ``cgw``      — entity-linked 1–2 hop graph + attached canonical claims + wiki
* ``baseline`` — the pre-CGW behaviour (whitespace LIKE over claims/relationships)

and reports entity-link hit rate, keyword coverage, claim/edge counts and
retrieval latency (p50 / p95). Answers are not generated here on purpose: this
measures retrieval quality deterministically and costs no LLM tokens.

Usage:
    python scripts/graph_acceptance.py [--golden scripts/graph_golden.yaml] \
        [--runs 5] [--json /tmp/graph_acceptance.json]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

import yaml
from sqlalchemy import or_

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.intelligence.graph_claim import retrieve
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import CanonicalClaim, Relationship


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _baseline(db, question: str) -> dict:
    """The old LIKE-based retrieval, kept only for comparison."""
    words = [w for w in question.lower().split() if len(w) > 3]
    claim_q = db.query(CanonicalClaim).filter(
        CanonicalClaim.status.in_(["active", "disputed"])
    )
    if words:
        claim_q = claim_q.filter(or_(*[CanonicalClaim.text.like(f"%{w}%") for w in words]))
    claims = claim_q.limit(12).all()

    rel_q = db.query(Relationship).filter(Relationship.status == "active")
    if words:
        rel_q = rel_q.filter(or_(*[
            Relationship.description.like(f"%{w}%")
            | Relationship.source_name.like(f"%{w}%")
            | Relationship.target_name.like(f"%{w}%")
            for w in words
        ]))
    rels = rel_q.limit(10).all()
    return {"claims": claims, "relationships": rels}


def _coverage(terms: list[str], texts: list[str]) -> float:
    if not terms:
        return 0.0
    joined = " ".join(_norm(t) for t in texts)
    hits = sum(1 for term in terms if _norm(term) in joined)
    return round(hits / len(terms), 3)


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return round(ordered[index], 1)


def evaluate(golden_path: str, runs: int) -> dict:
    with open(golden_path, encoding="utf-8") as handle:
        questions = yaml.safe_load(handle).get("questions", [])

    db = SessionLocal()
    rows = []
    latencies: list[float] = []
    try:
        for item in questions:
            question = item["question"]
            expected_entities = [e.lower() for e in item.get("expected_entities", [])]
            expected_terms = item.get("expected_terms", [])

            started = time.perf_counter()
            result = retrieve(db, question)
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)

            seeds = [
                {"name": s["name"], "aliases": [s.get("alias")] if s.get("alias") else []}
                for s in result.get("seeds", [])
            ]
            seed_names = [s["name"].lower() for s in seeds] + [
                a.lower() for s in seeds for a in s["aliases"] if a
            ]
            entity_hit = any(
                any(exp in name or name in exp for name in seed_names)
                for exp in expected_entities
            ) if expected_entities else None

            graph_texts = []
            for item_edge in result.get("edges", []):
                graph_texts.append(item_edge.get("description") or "")
                graph_texts.append(item_edge.get("source") or "")
                graph_texts.append(item_edge.get("target") or "")
            for claim_item in result.get("claims", []):
                graph_texts.append(claim_item["claim"].text)
            for page in result.get("wiki", []):
                graph_texts.append(page.get("content") or "")

            graph_terms = _coverage(expected_terms, graph_texts)

            base = _baseline(db, question)
            base_texts = []
            for claim in base["claims"]:
                base_texts.append(claim.text)
            for rel in base["relationships"]:
                base_texts.append(rel.description or "")
                base_texts.append(rel.source_name)
                base_texts.append(rel.target_name)
            base_terms = _coverage(expected_terms, base_texts)

            rows.append({
                "id": item.get("id"),
                "question": question,
                "entity_hit": entity_hit,
                "seeds": [s["name"] for s in seeds][:5],
                "edges": len(result.get("edges", [])),
                "claims": len(result.get("claims", [])),
                "wiki": len(result.get("wiki", [])),
                "term_coverage": graph_terms,
                "baseline_claims": len(base["claims"]),
                "baseline_relationships": len(base["relationships"]),
                "baseline_term_coverage": base_terms,
                "latency_ms": round(elapsed, 1),
            })

        # latency over repeated runs (first run warms caches)
        for _ in range(max(1, runs)):
            for item in questions:
                started = time.perf_counter()
                retrieve(db, item["question"])
                latencies.append((time.perf_counter() - started) * 1000)
    finally:
        db.close()

    hits = [r for r in rows if r["entity_hit"]]
    with_entities = [r for r in rows if r["entity_hit"] is not None]
    summary = {
        "questions": len(rows),
        "entity_link_rate": round(len(hits) / len(with_entities), 3) if with_entities else 0.0,
        "avg_term_coverage": round(statistics.mean([r["term_coverage"] for r in rows]), 3) if rows else 0.0,
        "avg_baseline_term_coverage": round(
            statistics.mean([r["baseline_term_coverage"] for r in rows]), 3
        ) if rows else 0.0,
        "avg_claims": round(statistics.mean([r["claims"] for r in rows]), 1) if rows else 0.0,
        "avg_edges": round(statistics.mean([r["edges"] for r in rows]), 1) if rows else 0.0,
        "latency_p50_ms": _p(latencies, 0.5),
        "latency_p95_ms": _p(latencies, 0.95),
        "latency_samples": len(latencies),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=os.path.join(os.path.dirname(__file__), "graph_golden.yaml"))
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    init_tables()
    report = evaluate(args.golden, args.runs)

    summary = report["summary"]
    print("== Graph acceptance ==")
    print(f"questions              : {summary['questions']}")
    print(f"entity link rate       : {summary['entity_link_rate']:.1%}")
    print(f"term coverage (CGW)    : {summary['avg_term_coverage']:.1%}")
    print(f"term coverage (baseline): {summary['avg_baseline_term_coverage']:.1%}")
    print(f"avg claims / edges     : {summary['avg_claims']} / {summary['avg_edges']}")
    print(f"latency p50 / p95      : {summary['latency_p50_ms']} ms / {summary['latency_p95_ms']} ms")
    print()
    print(f"{'id':5} {'hit':4} {'edges':5} {'claims':6} {'cov':5} {'base':5} {'ms':7} question")
    for row in report["rows"]:
        print(
            f"{row['id'] or '':5} {str(row['entity_hit'])[0]:4} {row['edges']:5} "
            f"{row['claims']:6} {row['term_coverage']:.2f}  {row['baseline_term_coverage']:.2f}  "
            f"{row['latency_ms']:7.1f} {row['question'][:60]}"
        )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f"\njson -> {args.json}")


if __name__ == "__main__":
    main()
