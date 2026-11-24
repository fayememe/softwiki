"""Graph x Claim x Wiki joint retrieval.

Why this module exists
----------------------
The answer engine used to "use" the knowledge graph by running a SQL ``LIKE``
over relationship descriptions, and "use" claims by running a ``LIKE`` over
canonical claim text. Both fail on Chinese questions (no whitespace tokenisation)
and neither does the one thing a graph is good at: link the question to entities,
walk a couple of hops, and come back with the claims attached to those edges.

This retriever implements the split described in
``docs/02-design/graph-claim-wiki.md``:

  * Graph  = routing/structure (entity linking + 1-2 hop neighbourhood)
  * Claim  = facts (canonical claims with status/evidence/pages)
  * Wiki   = narrative (compiled subject pages, only when fresh)
  * RAG    = untouched; answer_engine still runs the hybrid searcher

Everything here degrades to an empty result rather than raising, so the answer
path keeps working when a workspace has no graph or no wiki.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from softwiki.source_store.models import (
    CanonicalClaim,
    Claim,
    Entity,
    Relationship,
    WikiArtifactState,
)

logger = logging.getLogger(__name__)

MAX_SEEDS = int(os.getenv("CGW_MAX_SEEDS", "6"))
MAX_HOPS = int(os.getenv("CGW_MAX_HOPS", "2"))
MAX_EDGES = int(os.getenv("CGW_MAX_EDGES", "80"))
MAX_CLAIMS = int(os.getenv("CGW_MAX_CLAIMS", "16"))
MAX_WIKI = int(os.getenv("CGW_MAX_WIKI", "2"))
WIKI_CHARS = int(os.getenv("CGW_WIKI_CHARS", "1200"))

_ACTIVE_STATUSES = ("active", "disputed")
_NAME_SEP_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def normalize_name(text: str) -> str:
    """Case/punctuation-insensitive key used for name matching."""
    value = unicodedata.normalize("NFKC", text or "").lower()
    return _NAME_SEP_RE.sub(" ", value).strip()


def query_terms(question: str) -> list[str]:
    """Terms used for Chinese-aware matching.

    English: alphanumeric words of length >= 2.
    Chinese: character n-grams (4/3/2) so "低功耗特性" can match "低功耗".
    """
    normalized = normalize_name(question)
    terms: set[str] = set()
    for word in normalized.split():
        for ascii_token in _ASCII_RE.findall(word):
            if len(ascii_token) >= 2:
                terms.add(ascii_token)
        for cjk_run in _CJK_RE.findall(word):
            for size in (4, 3, 2):
                if len(cjk_run) < size:
                    continue
                for start in range(len(cjk_run) - size + 1):
                    terms.add(cjk_run[start:start + size])
    ordered = sorted(terms, key=lambda t: (len(t), t), reverse=True)
    return ordered[:40]


def _degrees(db: Session) -> dict[str, int]:
    """Relationship degree per normalized entity name (active edges only)."""
    rows = (
        db.query(Relationship.source_name, func.count(Relationship.id))
        .filter(Relationship.status == "active")
        .group_by(Relationship.source_name)
        .all()
    )
    rows += (
        db.query(Relationship.target_name, func.count(Relationship.id))
        .filter(Relationship.status == "active")
        .group_by(Relationship.target_name)
        .all()
    )
    degrees: dict[str, int] = {}
    for name, count in rows:
        key = normalize_name(name)
        if key:
            degrees[key] = degrees.get(key, 0) + int(count)
    return degrees


def _boundary_match(haystack: str, needle: str) -> bool:
    """Whole-token match for ASCII (so 'rm' does not match inside 'arm')."""
    if not needle:
        return False
    if not re.search(r"[a-z0-9]", needle):
        return needle in haystack
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def link_entities(db: Session, question: str, limit: int = MAX_SEEDS) -> list[dict[str, Any]]:
    """Deterministic entity linking: normalized substring + degree ranking."""
    qnorm = normalize_name(question)
    terms = set(query_terms(question))
    if not qnorm:
        return []

    degrees = _degrees(db)
    entities = db.query(Entity).all()

    seeds: list[dict[str, Any]] = []
    for entity in entities:
        key = normalize_name(entity.name)
        if len(key) < 2:
            continue

        score = 0.0
        if _boundary_match(qnorm, key):
            # Full entity name appears in the question.
            score = 10.0 + min(len(key), 40) / 10.0
        elif key in terms:
            score = 8.0 + min(len(key), 40) / 10.0
        else:
            words = key.split()
            if len(words) > 1 and all(len(w) >= 2 and w in terms for w in words):
                score = 6.0 + min(len(key), 40) / 20.0
            else:
                # A long distinctive term of the question is inside the name
                # ("M55" -> "Cortex-M55"). Short terms are ignored on purpose:
                # "arm" matches far too many names to be a useful seed.
                hits = [t for t in terms if len(t) >= 4 and t in key]
                if hits:
                    score = 4.0 + max(len(t) for t in hits) / 10.0

        if score <= 0:
            continue
        degree = degrees.get(key, 0)
        score += min(degree, 20) * 0.15
        seeds.append({
            "name": entity.name,
            "type": entity.type,
            "degree": degree,
            "score": round(score, 3),
        })

    seeds.sort(key=lambda s: (s["score"], s["degree"]), reverse=True)

    # "LSL" and "lsl" are separate Entity rows but the same seed for traversal.
    deduped: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for seed in seeds:
        key = normalize_name(seed["name"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(seed)
    return deduped[:limit]


def expand(
    db: Session,
    seeds: list[dict[str, Any]],
    max_hops: int = MAX_HOPS,
    max_edges: int = MAX_EDGES,
) -> list[dict[str, Any]]:
    """BFS over relationships stored by name (P0: no entity ids yet)."""
    if not seeds:
        return []

    # normalized key -> raw name as stored in the DB (edges use raw names)
    frontier: dict[str, str] = {}
    for seed in seeds:
        key = normalize_name(seed["name"])
        if key:
            frontier.setdefault(key, seed["name"])
    visited = set(frontier)
    seen_edges: set[int] = set()
    edges: list[dict[str, Any]] = []

    for hop in range(1, max_hops + 1):
        if not frontier or len(edges) >= max_edges:
            break
        display = sorted({name.lower() for name in frontier.values() if name})
        if not display:
            break

        rows = (
            db.query(Relationship)
            .filter(Relationship.status == "active")
            .filter(or_(
                func.lower(Relationship.source_name).in_(display),
                func.lower(Relationship.target_name).in_(display),
            ))
            .order_by(Relationship.confidence.desc(), Relationship.id.asc())
            .limit(max_edges * 3)
            .all()
        )

        next_frontier: dict[str, str] = {}
        for rel in rows:
            if rel.id in seen_edges:
                continue
            if len(edges) >= max_edges:
                break
            seen_edges.add(rel.id)
            edges.append({
                "id": rel.id,
                "source": rel.source_name,
                "target": rel.target_name,
                "relation_type": rel.relation_type,
                "description": rel.description,
                "confidence": rel.confidence if rel.confidence is not None else 1.0,
                "document_id": rel.document_id,
                "canonical_claim_id": rel.canonical_claim_id,
                "published_at": rel.published_at,
                "hop": hop,
            })
            for raw_name in (rel.source_name, rel.target_name):
                key = normalize_name(raw_name)
                if key and key not in visited:
                    visited.add(key)
                    next_frontier.setdefault(key, raw_name)

        frontier = next_frontier

    return edges


def _canonical_claims_for_edges(
    db: Session, edges: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """canonical_claim_id -> [{claim, hop, edge}]."""
    ids = {e["canonical_claim_id"] for e in edges if e.get("canonical_claim_id")}
    if not ids:
        return {}
    claims = (
        db.query(CanonicalClaim)
        .filter(CanonicalClaim.id.in_(ids))
        .filter(CanonicalClaim.status.in_(_ACTIVE_STATUSES))
        .all()
    )
    by_id: dict[str, dict[str, Any]] = {}
    for claim in claims:
        by_id[claim.id] = {"claim": claim, "hop": None, "edge": None}
    for edge in edges:
        entry = by_id.get(edge.get("canonical_claim_id") or "")
        if entry is None:
            continue
        if entry["hop"] is None or edge["hop"] < entry["hop"]:
            entry["hop"] = edge["hop"]
            entry["edge"] = edge
    return by_id


def _canonical_claims_for_seeds(
    db: Session, seeds: list[dict[str, Any]], per_seed: int = 6
) -> list[dict[str, Any]]:
    """Claims whose structured subject/object IS a seed entity."""
    names = [s["name"] for s in seeds]
    if not names:
        return []
    rows = (
        db.query(CanonicalClaim)
        .filter(CanonicalClaim.status.in_(_ACTIVE_STATUSES))
        .filter(or_(
            CanonicalClaim.subject.in_(names),
            CanonicalClaim.object.in_(names),
        ))
        .order_by(CanonicalClaim.evidence_count.desc(), CanonicalClaim.confidence.desc())
        .limit(per_seed * len(names))
        .all()
    )
    return [{"claim": row, "hop": 0, "edge": None} for row in rows]


def _raw_claims_for_edges(
    db: Session, edges: list[dict[str, Any]], limit: int = 12
) -> list[dict[str, Any]]:
    """Fallback for edges that are not projected onto a canonical claim."""
    doc_ids = {
        e["document_id"]
        for e in edges
        if not e.get("canonical_claim_id") and e.get("document_id")
    }
    if not doc_ids:
        return []
    rows = (
        db.query(Claim)
        .filter(Claim.document_id.in_(list(doc_ids)[:10]))
        .filter(Claim.status == "active")
        .order_by(Claim.confidence.desc())
        .limit(limit)
        .all()
    )
    hops = {
        e["document_id"]: e["hop"] for e in edges if e.get("document_id")
    }
    return [
        {"claim": row, "hop": hops.get(row.document_id, MAX_HOPS), "edge": None}
        for row in rows
    ]


def _claim_score(item: dict[str, Any]) -> float:
    claim = item["claim"]
    hop = item["hop"] if item["hop"] is not None else MAX_HOPS
    score = 4.0 / (1.0 + hop)
    edge = item.get("edge")
    if edge:
        score += 2.0 * float(edge.get("confidence") or 1.0)
    else:
        score += 1.0
    score += 1.5 * float(getattr(claim, "confidence", 0.5) or 0.5)
    evidence = int(getattr(claim, "evidence_count", 0) or 0)
    score += min(evidence, 5) * 0.2
    if getattr(claim, "status", "active") == "active":
        score += 0.4
    return round(score, 4)


def _collect_claims(db: Session, edges: list[dict[str, Any]],
                    seeds: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    canonical_items: list[dict[str, Any]] = []
    canonical_items.extend(_canonical_claims_for_edges(db, edges).values())
    canonical_items.extend(_canonical_claims_for_seeds(db, seeds))
    raw_items = _raw_claims_for_edges(db, edges)

    best: dict[str, dict[str, Any]] = {}
    for item in canonical_items:
        claim = item["claim"]
        item["score"] = _claim_score(item)
        current = best.get(claim.id)
        if current is None or item["score"] > current["score"]:
            best[claim.id] = item
    ranked = sorted(best.values(), key=lambda i: i["score"], reverse=True)

    raw_best: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        claim = item["claim"]
        item["score"] = _claim_score(item)
        current = raw_best.get(claim.id)
        if current is None or item["score"] > current["score"]:
            raw_best[claim.id] = item
    raw_ranked = sorted(raw_best.values(), key=lambda i: i["score"], reverse=True)

    return ranked[:MAX_CLAIMS], raw_ranked[:MAX_CLAIMS]


def _match_wiki(db: Session, seeds: list[dict[str, Any]],
                question: str) -> list[dict[str, Any]]:
    """Compiled subject pages for linked seeds (never stale pages)."""
    try:
        from softwiki.wiki.subject_pages import list_generated_pages, read_page
    except Exception as exc:  # pragma: no cover - import guard
        logger.debug("wiki subject pages unavailable: %s", exc)
        return []

    listing = list_generated_pages(db)
    if not listing.get("generated"):
        return []

    seed_keys = {normalize_name(s["name"]) for s in seeds}
    qnorm = normalize_name(question)
    matches = []
    for entry in listing.get("subjects", []):
        subject = entry.get("subject") or ""
        key = normalize_name(subject)
        if not key:
            continue
        if key not in seed_keys and key not in qnorm:
            continue
        state = (
            db.query(WikiArtifactState)
            .filter(WikiArtifactState.topic == subject)
            .first()
        )
        if state is not None and getattr(state, "stale_at", None) is not None:
            continue
        page = read_page(db, entry.get("slug") or "")
        if not page:
            continue
        content = page.get("content") or ""
        if len(content) > WIKI_CHARS:
            content = content[:WIKI_CHARS] + "\n…(truncated)"
        matches.append({
            "subject": subject,
            "slug": entry.get("slug"),
            "updated_at": entry.get("updated_at"),
            "claims_covered": entry.get("claims_covered"),
            "claims_total": entry.get("claims_total"),
            "content": content,
        })
        if len(matches) >= MAX_WIKI:
            break
    return matches


def retrieve(db: Session, question: str) -> dict[str, Any]:
    """Run the joint retrieval. Never raises into the answer path."""
    empty = {"seeds": [], "edges": [], "claims": [], "raw_claims": [], "wiki": []}
    if not question or not question.strip():
        return empty
    try:
        seeds = link_entities(db, question)
        if not seeds:
            return empty
        edges = expand(db, seeds)
        claims, raw_claims = _collect_claims(db, edges, seeds)
        wiki = _match_wiki(db, seeds, question)
        return {
            "seeds": seeds,
            "edges": edges,
            "claims": claims,
            "raw_claims": raw_claims,
            "wiki": wiki,
        }
    except Exception as exc:  # noqa: BLE001 - retrieval must degrade, not fail
        logger.warning("CGW retrieval failed, degrading: %s", exc)
        return empty


# --------------------------------------------------------------------------- #
# Prompt formatting
# --------------------------------------------------------------------------- #

def format_graph_context(result: dict[str, Any], limit: int = 12,
                         cite=None) -> list[str]:
    """One line per edge, ordered by hop then confidence."""
    edges = sorted(
        result.get("edges") or [],
        key=lambda e: (e.get("hop", 0), -(e.get("confidence") or 0.0)),
    )[:limit]
    lines = []
    for edge in edges:
        prefix = ""
        if cite and edge.get("document_id"):
            num = cite(edge["document_id"])
            if num:
                prefix = f"[{num}] "
        desc = (edge.get("description") or "").strip()
        if len(desc) > 160:
            desc = desc[:160] + "…"
        lines.append(
            f"- {prefix}(hop {edge.get('hop')}, conf {float(edge.get('confidence') or 1.0):.2f}) "
            f"{edge.get('source')} --({edge.get('relation_type')})--> {edge.get('target')}"
            + (f": {desc}" if desc else "")
        )
    return lines


def format_wiki_context(result: dict[str, Any]) -> list[str]:
    blocks = []
    for page in result.get("wiki") or []:
        blocks.append(
            f"--- Compiled Wiki: {page['subject']} "
            f"({page.get('claims_covered')}/{page.get('claims_total')} claims, "
            f"updated {page.get('updated_at') or 'unknown'}) ---\n"
            f"{page['content']}"
        )
    return blocks
