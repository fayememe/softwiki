"""Entity name normalization and deterministic resolution helpers.

Shared by the extractor (writes ``entities.normalized_name`` / aliases), the
normalization job (merges duplicates, rebuilds ids) and graph retrieval.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Iterable

_NAME_SEP_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")

# Ordinal/legal noise that must not make two spellings of the same IP distinct.
_SUFFIXES = (
    " limited", " ltd", " ltd.", " inc", " inc.", " corporation", " corp",
    " gmbh", " plc", " co.", " company",
)


def normalize_entity_name(name: str) -> str:
    value = unicodedata.normalize("NFKC", name or "").lower()
    value = _NAME_SEP_RE.sub(" ", value).strip()
    for suffix in _SUFFIXES:
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
            break
    return re.sub(r"\s+", " ", value)


def parse_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    return []


def clean_aliases(name: str, aliases: Iterable) -> list[str]:
    """Drop aliases equal to the entity name and duplicates (case-insensitive)."""
    base = normalize_entity_name(name)
    seen = {base}
    result = []
    for alias in aliases:
        alias = str(alias or "").strip()
        key = normalize_entity_name(alias)
        if not key or key in seen or len(alias) > 150:
            continue
        seen.add(key)
        result.append(alias)
    return result[:8]
