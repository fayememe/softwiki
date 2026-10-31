"""Cheap citation consistency check for grounded answers."""
from __future__ import annotations

import re
from typing import Iterable


def verify_citations(answer: str, citations: Iterable[dict]) -> dict:
    cited = {int(m) for m in re.findall(r"\[(\d+)\]", answer or "")}
    valid = {int(c.get("num")) for c in citations or [] if c.get("num") is not None}
    unknown = sorted(cited - valid)
    unused = sorted(valid - cited)
    warnings = []
    if valid and not cited:
        warnings.append("Answer has sources but no inline [n] citations.")
    if unknown:
        warnings.append(f"Unknown citation numbers: {unknown}")
    if unused:
        warnings.append(f"Sources not cited inline: {unused}")
    return {
        "valid_citations": sorted(valid),
        "cited": sorted(cited),
        "unknown": unknown,
        "unused": unused,
        "warnings": warnings,
    }
