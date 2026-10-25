"""Claim-to-wiki coverage metrics for the curated topic map."""
from __future__ import annotations

import os
from collections import Counter

import yaml
from sqlalchemy import func

from softwiki.config import get_config_path
from softwiki.source_store.models import Claim


def _topic_map() -> tuple[dict[str, str], set[str], set[str]]:
    path = get_config_path("topics.yaml")
    if not os.path.exists(path):
        return {}, set(), set()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    topics = data.get("topics", data) if isinstance(data, dict) else {}
    aliases: dict[str, str] = {}
    ignored: set[str] = set()
    if not isinstance(topics, dict):
        return {}, set(), set()
    for key, info in topics.items():
        info = info if isinstance(info, dict) else {}
        if key == "__ignore__":
            ignored.update(str(a) for a in (info.get("aliases") or []))
            continue
        aliases[key] = key
        for alias in info.get("aliases") or []:
            aliases[str(alias)] = key
    return aliases, ignored, set(topics.keys())


def compute_coverage(db) -> dict:
    aliases, ignored, canonical = _topic_map()
    rows = db.query(Claim.topic, func.count(Claim.id)).group_by(Claim.topic).all()
    total = 0
    mapped = 0
    ignored_count = 0
    unmapped = 0
    untagged = 0
    unmapped_topics: Counter[str] = Counter()
    mapped_topics: Counter[str] = Counter()

    for topic, count in rows:
        count = int(count or 0)
        total += count
        t = (topic or "").strip()
        if not t or t == "general":
            untagged += count
            unmapped += count
            unmapped_topics["(untagged)"] += count
        elif t in aliases:
            mapped += count
            mapped_topics[aliases[t]] += count
        elif t in ignored:
            ignored_count += count
        else:
            unmapped += count
            unmapped_topics[t] += count

    denom = max(1, total)
    effective_denom = max(1, mapped + unmapped)
    return {
        "total_claims": total,
        "mapped_claims": mapped,
        "ignored_claims": ignored_count,
        "unmapped_claims": unmapped,
        "untagged_claims": untagged,
        "coverage": round(mapped / denom, 4),
        "effective_coverage": round(mapped / effective_denom, 4),
        "canonical_topics": sorted(canonical - {"__ignore__"}),
        "mapped_topics": [
            {"topic": t, "claims": c} for t, c in mapped_topics.most_common(30)
        ],
        "unmapped_topics": [
            {"topic": t, "claims": c} for t, c in unmapped_topics.most_common(30)
        ],
        "ignored_topics_count": len(ignored),
    }
