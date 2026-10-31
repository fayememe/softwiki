#!/usr/bin/env python3
"""NLI/LLM conflict judge v0 (candidate generation + cached verdicts).

Dry-run by default. Use --apply to persist judgements and open contradictions.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import (
    CanonicalClaim, ClaimPairJudgement, Contradiction, Document,
)
from softwiki.knowledge.canonical import jaccard
from softwiki.knowledge.conflicts import _existing, _doc
from softwiki.knowledge.projections import reproject_claims
from softwiki.knowledge.wiki_queue import enqueue_wiki_rebuild
from softwiki.intelligence.llm_client import get_llm_client_and_params

PROMPT = """You are a technical fact-checker for ARM IP documentation.
Decide whether claim A and claim B assert incompatible facts for the same subject and scope.

Rules:
- Compatible if they describe different registers, fields, modes, revisions, conditions, or units.
- Compatible if one is a broader summary and the other a detail, without contradiction.
- Contradiction only if both cannot be true for the same subject/scope at the same revision.
- Do not use outside knowledge; use only the supplied text and source metadata.
Return ONLY JSON:
{"verdict":"contradiction|compatible|uncertain","severity":"high|medium|low","reason":"..."}
"""


def parse_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def candidates(db, limit: int):
    claims = db.query(CanonicalClaim).filter(
        CanonicalClaim.status.in_(["active", "disputed"]),
        CanonicalClaim.value_normalized.isnot(None),
    ).all()
    groups = {}
    for c in claims:
        groups.setdefault((c.topic, c.actor), []).append(c)
    out = []
    for group in groups.values():
        group = group[:80]
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.value_normalized == b.value_normalized:
                    continue
                score = jaccard(a.text, b.text)
                if score < 0.45:
                    continue
                x, y = sorted([a.id, b.id])
                if _existing(db, x, y, "source_conflict"):
                    continue
                if db.query(ClaimPairJudgement).filter(
                    ClaimPairJudgement.claim_a_id == x,
                    ClaimPairJudgement.claim_b_id == y,
                ).first():
                    continue
                out.append((score, a, b))
    out.sort(key=lambda x: x[0], reverse=True)
    return out[:max(1, limit)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    init_tables()
    db = SessionLocal()
    try:
        pairs = candidates(db, args.limit)
        print({"candidates": len(pairs)}, flush=True)
        if not pairs:
            return
        client, model, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        if not client:
            print({"error": "no LLM client configured"})
            return
        for score, a, b in pairs:
            da, db_doc = _doc(db, a), _doc(db, b)
            payload = {
                "topic": a.topic,
                "claim_a": {"text": a.text, "source": da.source_name if da else None,
                            "revision": da.revision if da else None},
                "claim_b": {"text": b.text, "source": db_doc.source_name if db_doc else None,
                            "revision": db_doc.revision if db_doc else None},
            }
            extra = {"max_tokens": max_tokens} if max_tokens else {}
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": PROMPT},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                temperature=temperature,
                **extra,
            )
            try:
                result = parse_json(resp.choices[0].message.content)
            except Exception as exc:
                print(f"[nli] parse failed: {exc}")
                continue
            verdict = str(result.get("verdict", "uncertain")).lower()
            severity = str(result.get("severity", "medium")).lower()
            reason = str(result.get("reason", ""))[:1000]
            print({"a": a.id, "b": b.id, "score": round(score, 3), "verdict": verdict,
                   "severity": severity, "reason": reason[:200]}, flush=True)
            if not args.apply:
                continue
            x, y = sorted([a.id, b.id])
            row = ClaimPairJudgement(
                claim_a_id=x, claim_b_id=y, model=model, verdict=verdict,
                reason=reason, severity=severity,
            )
            try:
                db.add(row)
                if verdict == "contradiction":
                    a.status = b.status = "disputed"
                    db.add(Contradiction(
                        claim_a_id=x, claim_b_id=y, type="source_conflict",
                        severity=severity if severity in ("high", "medium", "low") else "medium",
                        status="open", auto_resolved=False, resolution=reason or None,
                    ))
                db.commit()
                if verdict == "contradiction":
                    reproject_claims(db, [a.id, b.id])
                    enqueue_wiki_rebuild(db, [a.topic], reason="nli_conflict")
            except Exception as exc:
                db.rollback()
                print(f"[nli] persist failed: {exc}")
        print({"model": model, "applied": args.apply})
    finally:
        db.close()


if __name__ == "__main__":
    main()
