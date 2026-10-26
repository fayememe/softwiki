"""Claim-to-wiki coverage metrics for the curated topic map."""
from __future__ import annotations

import os
from collections import Counter
from fnmatch import fnmatch

import yaml
from sqlalchemy import func

from softwiki.config import get_config_path
from softwiki.source_store.models import Claim


def _topic_map() -> tuple[dict[str, str], list[tuple[str, str]], list[str], set[str]]:
    """Return exact aliases, (pattern, canonical) pairs, ignore patterns, pages."""
    path = get_config_path("topics.yaml")
    if not os.path.exists(path):
        return {}, [], [], set()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    topics = data.get("topics", data) if isinstance(data, dict) else {}
    if not isinstance(topics, dict):
        return {}, [], [], set()

    aliases: dict[str, str] = {}
    pattern_owners: list[tuple[str, str]] = []
    ignored: list[str] = []
    canonical: set[str] = set()

    for key, info in topics.items():
        info = info if isinstance(info, dict) else {}
        if key == "__ignore__":
            ignored.extend(str(a) for a in (info.get("aliases") or []))
            continue
        if info.get("kind") == "category":
            continue
        canonical.add(key)
        aliases[key] = key
        for alias in info.get("aliases") or []:
            alias = str(alias)
            if "*" in alias or "?" in alias:
                pattern_owners.append((alias, key))
            else:
                aliases[alias] = key
    return aliases, pattern_owners, ignored, canonical


def compute_coverage(db) -> dict:
    aliases, pattern_owners, ignored, canonical = _topic_map()
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
            continue

        owner = aliases.get(t)
        if owner is None:
            owner = next((key for pat, key in pattern_owners if fnmatch(t, pat)), None)
        if owner is not None:
            mapped += count
            mapped_topics[owner] += count
        elif t in ignored or any(fnmatch(t, pat) for pat in ignored):
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
        "canonical_topics": sorted(canonical),
        "mapped_topics": [
            {"topic": t, "claims": c} for t, c in mapped_topics.most_common(40)
        ],
        "unmapped_topics": [
            {"topic": t, "claims": c} for t, c in unmapped_topics.most_common(40)
        ],
        "ignored_topics_count": len(ignored),
    }
