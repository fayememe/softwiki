"""NLI/LLM conflict judge service (v0)."""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from sqlalchemy.orm import Session

from softwiki.source_store.models import CanonicalClaim, ClaimPairJudgement, Contradiction
from softwiki.knowledge.canonical import jaccard
from softwiki.knowledge.conflicts import _existing, _doc
from softwiki.knowledge.projections import reproject_claims
from softwiki.knowledge.wiki_queue import enqueue_wiki_rebuild
from softwiki.intelligence.llm_client import get_llm_client_and_params

LEGAL_RE = re.compile(r"copyright|licen[cs]e|warranty|disclaimer|confidential|trademark|patent", re.IGNORECASE)
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


def candidates(db: Session, limit: int):
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
                if LEGAL_RE.search(a.text or "") or LEGAL_RE.search(b.text or ""):
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


def judge_candidates(db: Session, limit: int = 10, apply: bool = False,
                     judge: Optional[Callable] = None) -> dict:
    pairs = candidates(db, limit)
    results = []
    if not pairs:
        return {"candidates": 0, "results": [], "applied": apply}
    if judge is None:
        client, model, temperature, max_tokens = get_llm_client_and_params("cheap_extraction")
        if not client:
            return {"candidates": len(pairs), "results": [], "error": "no LLM client configured", "applied": apply}

        def judge(a, b, da, db_doc):
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
            result = parse_json(resp.choices[0].message.content)
            result["_model"] = model
            return result

    for score, a, b in pairs:
        da, db_doc = _doc(db, a), _doc(db, b)
        try:
            result = judge(a, b, da, db_doc)
        except Exception as exc:
            results.append({"a": a.id, "b": b.id, "error": str(exc)})
            continue
        verdict = str(result.get("verdict", "uncertain")).lower()
        severity = str(result.get("severity", "medium")).lower()
        reason = str(result.get("reason", ""))[:1000]
        model = result.get("_model", "injected-judge")
        item = {"a": a.id, "b": b.id, "score": round(score, 3),
                "verdict": verdict, "severity": severity, "reason": reason}
        results.append(item)
        if not apply:
            continue
        x, y = sorted([a.id, b.id])
        try:
            db.add(ClaimPairJudgement(
                claim_a_id=x, claim_b_id=y, model=model, verdict=verdict,
                reason=reason, severity=severity,
            ))
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
            item["persist_error"] = str(exc)
    return {"candidates": len(pairs), "results": results, "applied": apply}
