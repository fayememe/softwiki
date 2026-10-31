#!/usr/bin/env python3
"""Optional v0 structured-claim pass for conflict precision.

Extracts subject / predicate / object / qualifiers from canonical claim text.
Run sparingly: one LLM call per batch of 10 claims.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import CanonicalClaim
from softwiki.knowledge.canonical import normalize_text
from softwiki.intelligence.llm_client import get_llm_client_and_params

PROMPT = """Extract one factual assertion from each technical claim.
Return ONLY a JSON array, one object per input id:
{"id":"...","is_factual":true,"subject":"entity/register/field","predicate":"property/relation","object":"value/behavior","qualifiers":{"scope":"","condition":"","version":"","unit":""}}
Rules:
- subject and predicate must be short noun/verb phrases, not full sentences.
- object is the asserted value/behavior (e.g. "0x0", "32-bit", "read-only").
- qualifiers capture version, condition, mode, unit; omit irrelevant keys.
- is_factual=false for opinions, recommendations, marketing, or non-assertions.
- Never invent IDs.
"""


def parse_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--topic", default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    init_tables()
    db = SessionLocal()
    try:
        q = db.query(CanonicalClaim).filter(
            CanonicalClaim.status.in_(["active", "disputed"]),
            CanonicalClaim.subject.is_(None),
        )
        if args.topic:
            q = q.filter(CanonicalClaim.topic == args.topic)
        claims = q.order_by(CanonicalClaim.id).limit(max(1, args.limit)).all()
        if not claims:
            print({"claims": 0, "reason": "nothing to structure"})
            return
        client, model, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        if not client:
            print({"error": "no LLM client configured"})
            return
        updated = 0
        for i in range(0, len(claims), args.batch):
            batch = claims[i:i + args.batch]
            payload = [{"id": c.id, "text": c.text[:1500]} for c in batch]
            extra = {"max_tokens": max_tokens} if max_tokens else {}
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": PROMPT},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                temperature=temperature,
                **extra,
            )
            try:
                rows = parse_json(resp.choices[0].message.content)
            except Exception as exc:
                print(f"[structure] parse failed: {exc}: {resp.choices[0].message.content[:300]}")
                continue
            by_id = {str(r.get("id")): r for r in rows if isinstance(r, dict)}
            for c in batch:
                row = by_id.get(c.id)
                if not row or not row.get("is_factual", True):
                    continue
                subject = (row.get("subject") or "").strip()[:300]
                predicate = (row.get("predicate") or "").strip()[:200]
                obj = (row.get("object") or "").strip()[:500]
                if not subject or not predicate or not obj:
                    continue
                qualifiers = row.get("qualifiers") or {}
                c.subject = subject
                c.predicate = predicate
                c.object = obj
                c.qualifiers = json.dumps(qualifiers, ensure_ascii=False, sort_keys=True)
                base = "|".join([normalize_text(subject), normalize_text(predicate),
                                 normalize_text(c.qualifiers), normalize_text(obj)])
                c.structure_hash = hashlib.sha256(base.encode("utf-8")).hexdigest()
                updated += 1
            print(f"[structure] {min(i + args.batch, len(claims))}/{len(claims)}", flush=True)
            if args.apply:
                db.commit()
        if not args.apply:
            db.rollback()
        print({"claims": len(claims), "updated": updated, "model": model, "applied": args.apply})
    finally:
        db.close()


if __name__ == "__main__":
    main()
