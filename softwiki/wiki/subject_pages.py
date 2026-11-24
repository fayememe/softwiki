"""Subject-granular wiki pages: one entity per page.

Why: the topic-based generator put 6,678 canonical claims into a single 28 KB
page (silently truncated to 250). A pilot showed one page per subject keeps the
model's discrimination — it separates tangential claims, surfaces conflicts, and
cites sources — up to roughly 25 claims, and degrades into transcription beyond
~50.

See docs/02-design/wiki-page-granularity.md.

Invariants:
  * A page never silently drops claims. Over the limit it is split (or fails),
    and every page records claims_covered / claims_total.
  * SUBJECT_PAGE_CLAIM_LIMIT is a fixed cap, not a target.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from softwiki.source_store.models import (
    CanonicalClaim,
    Document,
    Entity,
    Relationship,
)

# Fixed cap per page. Not configurable at runtime on purpose: a drifting limit
# makes pages incomparable across time (see the design doc, decision D1).
SUBJECT_PAGE_CLAIM_LIMIT = int(os.getenv("WIKI_SUBJECT_PAGE_CLAIM_LIMIT", "25"))

# A subject needs at least this many relationships to deserve its own page.
# 70% of entities appear in 1-2 relationships only — extraction noise.
DEFAULT_MIN_RELATIONS = int(os.getenv("WIKI_SUBJECT_MIN_RELATIONS", "5"))

# ...and at least this many claims. A subject with one claim produces a page
# that is a single sentence (e.g. "Starbucks Corporation" vs "Starbucks"), which
# adds navigation noise without adding knowledge.
DEFAULT_MIN_CLAIMS = int(os.getenv("WIKI_SUBJECT_MIN_CLAIMS", "5"))

SYSTEM_PROMPT = """You are compiling a wiki entry for ONE subject from a knowledge base.

Hard rules:
- Use ONLY the numbered claims below. No outside knowledge, no inference beyond them.
- Every sentence stating a fact must end with the claim number in brackets, e.g. [3].
- If claims disagree, say so explicitly under "Conflicts" and cite both numbers.
  Never silently pick one.
- If a claim is only tangentially about the subject (e.g. it mentions the subject
  while discussing a different product), put it under "Mentions", not "Facts".
- The summary paragraph must state what the subject IS and where its boundaries
  lie. Do NOT restate facts that appear under "Facts".
- Do not invent sections. Omit any section with nothing to say.

Structure:
# <Subject>

one-paragraph summary (definition and scope only)

## Facts
(organized by theme, each line cited)

## Conflicts
(only if claims disagree)

## Mentions
(only if some claims are tangential)

## Sources
(claim number -> document title)
"""


def _slugify(name: str) -> str:
    import unicodedata

    # Fold accents so "Nestlé" becomes "nestle" rather than "nestl".
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug or hashlib.sha1(name.encode()).hexdigest()[:10]


def _pages_dir(db: Session) -> str:
    from softwiki.config import get_export_dir

    return get_export_dir("wiki/pages")


# --------------------------------------------------------------------------- #
# Subject discovery
# --------------------------------------------------------------------------- #

# Candidate lists are a read-only projection of the graph; recomputing them on
# every panel open is wasted work. Short TTL so new claims show up soon.
_CANDIDATE_TTL = float(os.getenv("WIKI_CANDIDATE_TTL_SECONDS", "120"))
_candidate_cache: dict[tuple, tuple[float, list[dict]]] = {}


def invalidate_candidates() -> None:
    _candidate_cache.clear()


def subject_candidates(db: Session, min_relations: int = DEFAULT_MIN_RELATIONS,
                       limit: int | None = None, use_cache: bool = True) -> list[dict]:
    """Rank entities by how well connected they are.

    Relationship endpoints are stored by name (not id), so degree is counted by
    name. Entities below `min_relations` are treated as noise.
    """
    key = (_workspace_key(), min_relations, limit, DEFAULT_MIN_CLAIMS)
    now = time.monotonic()
    if use_cache:
        cached = _candidate_cache.get(key)
        if cached and now - cached[0] < _CANDIDATE_TTL:
            return cached[1]

    from sqlalchemy import union_all

    src = db.query(Relationship.source_name.label("name"))
    dst = db.query(Relationship.target_name.label("name"))
    endpoints = union_all(src, dst).subquery()

    degree_rows = (
        db.query(endpoints.c.name, func.count().label("degree"))
        .group_by(endpoints.c.name)
        .having(func.count() >= min_relations)
        .subquery()
    )

    rows = (
        db.query(
            degree_rows.c.name,
            degree_rows.c.degree,
            Entity.type,
            Entity.description,
        )
        .join(Entity, Entity.name == degree_rows.c.name)
        .order_by(degree_rows.c.degree.desc())
        .limit(limit or 100000)
        .all()
    )

    from softwiki.wiki.subject_rules import ignored

    skip = ignored()

    # One query for all counts. The old code issued one COUNT per entity (436
    # round trips on armkb = ~33s per panel open); a VALUES join does it once.
    names = [row[0] for row in rows]
    counts = _claim_counts(db, names)
    total_claims = (
        db.query(func.count(CanonicalClaim.id))
        .filter(CanonicalClaim.status.in_(("active", "disputed")))
        .scalar()
        or 0
    )
    theme_share = float(os.getenv("WIKI_SUBJECT_THEME_SHARE", "0.15"))

    out: list[dict] = []
    for name, degree, etype, desc in rows:
        if name in skip:
            continue
        claim_count = counts.get(name, 0)
        if claim_count == 0 or claim_count < DEFAULT_MIN_CLAIMS:
            # No claims, or a single sentence's worth: noise, not knowledge.
            continue
        if total_claims and claim_count / total_claims >= theme_share:
            # The library's own theme, not a subject: splitting it would just
            # restate the whole corpus page by page.
            continue
        out.append({
            "subject": name,
            "slug": _slugify(name),
            "type": etype or "concept",
            "degree": int(degree),
            "claims_total": claim_count,
            "page_count": 1 + (claim_count - 1) // SUBJECT_PAGE_CLAIM_LIMIT,
            "needs_split": claim_count > SUBJECT_PAGE_CLAIM_LIMIT,
            "description": (desc or "")[:300],
        })
    if use_cache:
        _candidate_cache[key] = (now, out)
    return out


def _workspace_key() -> str:
    from softwiki.config import get_workspace_dir

    try:
        return os.path.basename(get_workspace_dir())
    except Exception:  # noqa: BLE001 - cache key must never break the request
        return "unknown"


def _claim_counts(db: Session, names: list[str]) -> dict[str, int]:
    """Claims per subject in a single round trip.

    `subject` is preferred but null for most rows, so the text match is the
    fallback. LIKE works on both PostgreSQL and SQLite (the test suite uses the
    latter); entity names do not normally contain wildcards.
    """
    if not names:
        return {}
    from sqlalchemy import text as sql_text

    values = ", ".join(f"(:n{i})" for i in range(len(names)))
    params = {f"n{i}": name for i, name in enumerate(names)}
    sql = sql_text(
        f"""
        WITH names(name) AS (VALUES {values})
        SELECT names.name, count(c.id)
        FROM names
        LEFT JOIN canonical_claims c
          ON c.status IN ('active', 'disputed')
         AND (c.subject = names.name
              OR lower(c.text) LIKE '%' || lower(names.name) || '%')
        GROUP BY names.name
        """
    )
    return {row[0]: int(row[1] or 0) for row in db.execute(sql, params).fetchall()}


def _is_library_theme(db: Session, name: str) -> bool:
    """True when an "entity" is really the whole knowledge base's theme.

    In a coffee KB the entity `Coffee` matches 3,464 of 6,686 claims. Treated as
    a subject it would split into ~140 pages that together re-state the corpus —
    that is the old mega-page problem wearing a different hat. A library theme is
    recognised by covering a large share of the corpus.
    """
    threshold = float(os.getenv("WIKI_SUBJECT_THEME_SHARE", "0.15"))
    total = (
        db.query(func.count(CanonicalClaim.id))
        .filter(CanonicalClaim.status.in_(("active", "disputed")))
        .scalar()
        or 0
    )
    if total == 0:
        return False
    covered = claim_count_for_subject(db, name)
    return covered / total >= threshold


def claim_count_for_subject(db: Session, subject: str) -> int:
    return (
        db.query(func.count(CanonicalClaim.id))
        .filter(
            CanonicalClaim.status.in_(("active", "disputed")),
            _subject_match(subject),
        )
        .scalar()
        or 0
    )


def _subject_match(subject: str):
    """Match a subject against a claim.

    Prefers the structured `subject` column; falls back to a text match so the
    feature works before claim structuring is complete (coffee: subject is null
    for most claims).
    """
    return or_(
        CanonicalClaim.subject == subject,
        CanonicalClaim.text.ilike(f"%{subject}%"),
    )


def claims_for_subject(db: Session, subject: str) -> list[CanonicalClaim]:
    return (
        db.query(CanonicalClaim)
        .filter(
            CanonicalClaim.status.in_(("active", "disputed")),
            _subject_match(subject),
        )
        .order_by(CanonicalClaim.confidence.desc(), CanonicalClaim.id)
        .all()
    )


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #

def _claim_source_label(claim: CanonicalClaim, doc_title: str | None,
                        doc_actor: str | None) -> str:
    title = (doc_title or "").strip()
    # Placeholder titles produced when extraction fails; prefer actor, else drop.
    if not title or title.lower() in {"document", "untitled", "untitled document"}:
        title = ""
    if not title:
        actor = (doc_actor or "").strip()
        title = actor if actor and actor.lower() not in {"document", "study authors"} else ""
    if claim.primary_page_start is not None:
        span = (
            f"p.{claim.primary_page_start}"
            if claim.primary_page_end in (None, claim.primary_page_start)
            else f"p.{claim.primary_page_start}-{claim.primary_page_end}"
        )
        return f"{title}, {span}" if title else span
    return title or "source unavailable"


def _build_prompt(subject: str, claims: list[CanonicalClaim],
                  labels: list[str], part: tuple[int, int] | None) -> str:
    lines = [f"Subject: {subject}", ""]
    if part:
        lines.append(f"This is part {part[0]} of {part[1]} for a large subject.")
        lines.append("")
    lines.append("Claims:")
    lines.append("")
    for i, (claim, label) in enumerate(zip(claims, labels), 1):
        text = (claim.text or "").strip().replace("\n", " ")
        lines.append(f"[{i}] ({label}) {text}")
    return "\n".join(lines)


def _split_claims(claims: list[CanonicalClaim], part_size: int) -> list[list[CanonicalClaim]]:
    """Split oversized subjects into parts of at most `part_size`.

    Grouping by relationship type was the design intent, but a stable, explainable
    split is better than an ad-hoc semantic one: parts are formed by ordering on
    confidence/date and cutting at the limit, and the parent index page lists all
    parts so nothing is lost.
    """
    return [claims[i:i + part_size] for i in range(0, len(claims), part_size)]


def generate_subject_pages(db: Session, subject: str, *,
                           intervention: str | None = None,
                           force: bool = False,
                           oversize: str = "split") -> dict:
    """Generate the page(s) for one subject.

    Returns a summary dict. Raises ValueError when `oversize="fail"` and the
    subject exceeds the cap — the caller must never fall back to truncation.
    """
    from softwiki.intelligence.llm_client import get_llm_client_and_params

    from softwiki.wiki.subject_rules import ignored, locked

    if subject in ignored():
        raise ValueError(
            f"subject '{subject}' is marked ignore in config/wiki_subjects.yaml"
        )
    if subject in locked() and not force:
        # A hand-edited page: the generator must not overwrite it.
        return {"subject": subject, "skipped": "locked", "pages": []}

    claims = claims_for_subject(db, subject)
    total = len(claims)
    if total == 0:
        raise ValueError(f"subject '{subject}' has no active claims")

    if total > SUBJECT_PAGE_CLAIM_LIMIT and oversize == "fail":
        raise ValueError(
            f"subject '{subject}' has {total} claims, above the fixed page limit "
            f"{SUBJECT_PAGE_CLAIM_LIMIT}; refusing to truncate (oversize=fail)"
        )

    client, model, temperature, max_tokens = get_llm_client_and_params("wiki_compilation")
    if client is None:
        raise RuntimeError(
            "no usable LLM client for wiki_compilation; check model profile / keys"
        )

    out_dir = _pages_dir(db)
    os.makedirs(out_dir, exist_ok=True)

    slug = _slugify(subject)
    parts = _split_claims(claims, SUBJECT_PAGE_CLAIM_LIMIT)
    written: list[dict] = []

    for idx, part_claims in enumerate(parts, 1):
        part_name = slug if len(parts) == 1 else f"{slug}-p{idx}"
        labels = []
        for c in part_claims:
            doc = (
                db.query(Document).filter(Document.id == c.primary_document_id).first()
                if c.primary_document_id else None
            )
            labels.append(
                _claim_source_label(c, doc.title if doc else None, doc.author if doc else None)
            )

        prompt = _build_prompt(
            subject, part_claims, labels,
            (idx, len(parts)) if len(parts) > 1 else None,
        )
        system = SYSTEM_PROMPT
        if intervention:
            system += "\n\n## USER INTERVENTIONS (highest priority)\n" + intervention

        resp = client.chat.completions.create(
            model=model,
            temperature=temperature if temperature is not None else 0.0,
            max_tokens=max_tokens or 8000,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content or ""
        finish = resp.choices[0].finish_reason
        usage = resp.usage
        generated_at = datetime.utcnow().isoformat(timespec="seconds")

        header = (
            f"<!-- subject={subject} slug={part_name} "
            f"claims_covered={len(part_claims)} claims_total={total} "
            f"model={model} finish={finish} generated_at={generated_at} -->\n"
        )
        path = os.path.join(out_dir, f"{part_name}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + content)

        written.append({
            "slug": part_name,
            "part": idx,
            "parts": len(parts),
            "path": path,
            "claims_covered": len(part_claims),
            "finish": finish,
            "chars": len(content),
            "tokens_in": getattr(usage, "prompt_tokens", None),
            "tokens_out": getattr(usage, "completion_tokens", None),
        })

    _update_index(db, subject, slug, out_dir, total, written, model, parts)
    return {
        "subject": subject,
        "slug": slug,
        "claims_total": total,
        "pages": written,
        "model": model,
    }


def _update_index(db: Session, subject: str, slug: str, out_dir: str,
                  total: int, written: list[dict], model: str,
                  parts: list) -> None:
    index_path = os.path.join(out_dir, "index.json")
    data: dict = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
    entries = {
        e.get("slug", ""): e
        for e in data.get("subjects", [])
        if isinstance(e, dict) and e.get("slug")
    }
    entries[slug] = {
        "subject": subject,
        "slug": slug,
        "claims_total": total,
        "claims_covered": sum(w["claims_covered"] for w in written),
        "pages": [w["slug"] for w in written],
        "parts": len(parts),
        "needs_split": len(parts) > 1,
        "model": model,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
    }
    subjects = sorted(entries.values(), key=lambda e: e["subject"].lower())
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"subjects": subjects}, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def list_generated_pages(db: Session) -> dict:
    out_dir = _pages_dir(db)
    index_path = os.path.join(out_dir, "index.json")
    if not os.path.exists(index_path):
        return {"subjects": [], "pages_dir": out_dir, "generated": False}
    try:
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"subjects": [], "pages_dir": out_dir, "generated": False,
                "error": str(exc)}
    return {"subjects": data.get("subjects", []), "pages_dir": out_dir, "generated": True}


def read_page(db: Session, slug: str) -> dict | None:
    """Read one generated page, resolving both part pages and parent indexes."""
    out_dir = _pages_dir(db)
    safe = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    if not safe:
        return None

    path = os.path.join(out_dir, f"{safe}.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    meta: dict = {}
    if raw.startswith("<!--"):
        end = raw.find("-->")
        if end > 0:
            for token in raw[4:end].split():
                if "=" in token:
                    k, v = token.split("=", 1)
                    meta[k] = v

    return {"slug": safe, "content": raw, "meta": meta}


def read_subject_page(db: Session, subject: str, max_parts: int = 2) -> dict | None:
    """Read a subject page even when it was split into part pages.

    Split subjects have an index entry whose ``slug`` has no .md file; the
    content lives in ``<slug>-p1.md`` ... Readers used to miss those entirely.
    """
    listing = list_generated_pages(db)
    target = _slugify(subject)
    entry = next(
        (e for e in listing.get("subjects", []) if e.get("subject") == subject),
        None,
    )
    if entry is None:
        entry = next(
            (e for e in listing.get("subjects", []) if e.get("slug") == target),
            None,
        )
    if entry is None:
        return read_page(db, target)

    parts = entry.get("pages") or [entry.get("slug")]
    contents = []
    for slug in parts[:max_parts]:
        page = read_page(db, slug)
        if page:
            contents.append(page.get("content") or "")
    if not contents:
        return None
    return {
        "slug": entry.get("slug") or target,
        "content": "\n\n".join(contents),
        "meta": {"parts": len(parts), "read": len(contents)},
    }
