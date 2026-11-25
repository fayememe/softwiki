#!/usr/bin/env python3
"""Build a static wiki portal (wikiweb) from the knowledge base.

This is the deterministic counterpart to the earlier agent-generated portal:
same shell/CSS/JS as the existing Coffee portal, but every fact, timeline
entry, connection and reference comes from the database. Re-running it updates
content without changing the framework.

Layout (matches WIKIWEB_ENTRY=<kb>/index.html):

    <out-root>/
      assets/wiki.css, assets/wiki.js
      <kb>/index.html, all.html, timeline.html, about.html
      <kb>/search-index.json
      <kb>/category/<type>.html
      <kb>/wiki/<slug>.html

Usage:
    python scripts/wikiweb_build.py --out-root /data/workspaces/armkb/exports/wikiweb \
        --kb-dir armkb --kb-label ARM --limit 300 --min-claims 3
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from softwiki.source_store.db import SessionLocal
from softwiki.source_store.models import (
    CanonicalClaim,
    ClaimEvidence,
    Document,
    Entity,
    Event,
    Relationship,
)

DEFAULT_ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "softwiki", "templates", "wikiweb",
)

TYPE_LABELS = {
    "product": "Products",
    "ip_block": "IP blocks",
    "architecture": "Architectures",
    "protocol": "Protocols",
    "instruction_set": "Instruction sets",
    "feature": "Features",
    "register": "Registers",
    "component": "Components",
    "standard": "Standards",
    "organization": "Organizations",
    "concept": "Concepts",
    "project": "Projects",
    "location": "Places",
    "person": "People",
    "country": "Countries",
    "other": "Other",
}

TYPE_ORDER = [
    "product", "ip_block", "architecture", "protocol", "instruction_set",
    "feature", "register", "component", "standard", "organization",
    "concept", "project", "location", "person", "country", "other",
]

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return SLUG_RE.sub("-", (name or "").lower()).strip("-") or "item"


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def domain(url: str | None) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def type_label(entity_type: str | None) -> str:
    return TYPE_LABELS.get((entity_type or "other").lower(), (entity_type or "Other").title())


def _plain_markdown(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_>#]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- #
# shell
# --------------------------------------------------------------------------- #

def shell(title: str, kb_label: str, base: str, catalog: dict, body: str,
          subtitle: str = "Knowledge Wiki", asset_base: str = "") -> str:
    cats = "".join(
        f'<li><a href="{base}category/{t}.html">{esc(type_label(t))}</a></li>'
        for t in catalog["category_order"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — {esc(kb_label)} Wiki</title>
<link rel="stylesheet" href="{asset_base}assets/wiki.css">
</head>
<body data-base="{base}" data-kb="{esc(kb_label)}">
<header class="site-head">
  <div class="head-inner">
    <a class="brand" href="{base}index.html"><span class="brand-mark">W</span><span class="brand-text">{esc(kb_label)}<small>{esc(subtitle)}</small></span></a>
    <div class="search-wrap">
      <input id="wiki-search" type="search" placeholder="Search {esc(kb_label)}…" autocomplete="off" aria-label="Search">
      <div id="search-results" class="search-results" hidden></div>
    </div>
    <nav class="top-nav">
      <a href="{base}index.html">Main</a>
      <a href="{base}all.html">All</a>
      <a href="{base}timeline.html">Timeline</a>
      <a href="#" id="random-link">Random</a>
    </nav>
  </div>
</header>
<div class="shell">
  <aside class="sidebar">
    <nav>
      <a href="{base}index.html">Main page</a>
      <a href="{base}all.html">All articles</a>
      <a href="{base}timeline.html">Timeline</a>
      <a href="{base}about.html">About this wiki</a>
    </nav>
    <div class="side-h">Categories</div>
    <ul class="side-cats">{cats}</ul>
    <div class="side-note">Generated from the {esc(kb_label)} knowledge base: claims, relationships, events and sources.</div>
  </aside>
  <main class="content">
{body}
  </main>
</div>
<footer class="site-foot">
  <span>{esc(kb_label)} Wiki</span>
  <span>Built from structured knowledge-base claims · <a href="{base}about.html">method</a></span>
</footer>
<script src="{asset_base}assets/wiki.js"></script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# data assembly
# --------------------------------------------------------------------------- #

def pick_entities(db: Session, limit: int, min_claims: int) -> tuple[list[dict], dict]:
    degree = defaultdict(int)
    for col in (Relationship.source_entity_id, Relationship.target_entity_id):
        rows = (
            db.query(col, func.count())
            .filter(Relationship.status == "active")
            .filter(col.isnot(None))
            .group_by(col)
            .all()
        )
        for entity_id, count in rows:
            degree[entity_id] += int(count)

    # Legacy/mid-migration data may not have entity ids on edges yet; fall back
    # to name-based degree so the portal is never empty.
    if not degree:
        name_degree: dict[str, int] = defaultdict(int)
        for source, target in (
            db.query(Relationship.source_name, Relationship.target_name)
            .filter(Relationship.status == "active")
            .all()
        ):
            name_degree[(source or "").lower()] += 1
            name_degree[(target or "").lower()] += 1
        for entity in db.query(Entity).filter(Entity.merged_into.is_(None)).all():
            degree[entity.id] = name_degree.get((entity.name or "").lower(), 0)

    claim_ids: dict[int, set[str]] = defaultdict(set)
    for src, claim in (
        db.query(Relationship.source_entity_id, Relationship.canonical_claim_id)
        .filter(Relationship.status == "active")
        .filter(Relationship.canonical_claim_id.isnot(None))
        .all()
    ):
        if src:
            claim_ids[src].add(claim)
    for dst, claim in (
        db.query(Relationship.target_entity_id, Relationship.canonical_claim_id)
        .filter(Relationship.status == "active")
        .filter(Relationship.canonical_claim_id.isnot(None))
        .all()
    ):
        if dst:
            claim_ids[dst].add(claim)

    entities = db.query(Entity).filter(Entity.merged_into.is_(None)).all()
    rows = []
    for entity in entities:
        deg = degree.get(entity.id, 0)
        claims = claim_ids.get(entity.id, set())
        if deg == 0 and not claims:
            continue
        score = deg + 2 * len(claims)
        rows.append({
            "id": entity.id, "name": entity.name, "type": entity.type or "other",
            "description": entity.description or "", "degree": deg,
            "claim_count": len(claims), "claims": claims, "score": score,
        })
    rows.sort(key=lambda r: (r["score"], r["degree"]), reverse=True)
    selected = [r for r in rows if r["claim_count"] >= min_claims][:limit]
    if not selected:
        selected = rows[:limit]
    catalog = {
        "category_order": [t for t in TYPE_ORDER
                           if any(r["type"] == t for r in selected)],
        "by_type": defaultdict(list),
    }
    for row in selected:
        catalog["by_type"][row["type"]].append(row)
    return selected, catalog


def load_claims(db: Session, selected: list[dict]) -> dict[str, list[dict]]:
    names = [row["name"] for row in selected]
    ids = set()
    for row in selected:
        ids |= row["claims"]

    by_name = {row["name"]: row for row in selected}
    result: dict[str, list[CanonicalClaim]] = defaultdict(list)
    for row in selected:
        if row["claims"]:
            claims = db.query(CanonicalClaim).filter(CanonicalClaim.id.in_(row["claims"])).all()
            result[row["name"]].extend(claims)
    structured = (
        db.query(CanonicalClaim)
        .filter(CanonicalClaim.status.in_(["active", "disputed"]))
        .filter(or_(CanonicalClaim.subject.in_(names), CanonicalClaim.object.in_(names)))
        .all()
    )
    for claim in structured:
        for key in (claim.subject, claim.object):
            if key in by_name and claim not in result[key]:
                result[key].append(claim)

    out: dict[str, list[dict]] = {}
    for name, claims in result.items():
        seen = set()
        items = []
        for claim in claims:
            if claim.id in seen:
                continue
            seen.add(claim.id)
            items.append({
                "id": claim.id, "text": claim.text, "actor": claim.actor,
                "status": claim.status, "confidence": claim.confidence or 0.0,
                "published": claim.valid_from, "evidence": claim.evidence_count or 0,
                "doc_id": claim.primary_document_id,
                "page": claim.primary_page_start,
            })
        items.sort(key=lambda c: (c["status"] != "active", -(c["confidence"] or 0)))
        out[name] = items
    return out


def load_edges(db: Session, selected: list[dict]) -> dict[str, list[dict]]:
    ids = [row["id"] for row in selected]
    edges: dict[int, list[dict]] = defaultdict(list)
    rows = (
        db.query(Relationship)
        .filter(Relationship.status == "active")
        .filter(or_(Relationship.source_entity_id.in_(ids),
                    Relationship.target_entity_id.in_(ids)))
        .order_by(Relationship.weight.desc(), Relationship.confidence.desc())
        .limit(20000)
        .all()
    )
    for rel in rows:
        payload = {
            "type": rel.relation_type, "description": rel.description or "",
            "weight": float(rel.weight or 1.0), "confidence": float(rel.confidence or 1.0),
            "doc_id": rel.document_id, "claim": rel.canonical_claim_id,
            "source": rel.source_name, "target": rel.target_name,
            "source_id": rel.source_entity_id, "target_id": rel.target_entity_id,
        }
        for entity_id in (rel.source_entity_id, rel.target_entity_id):
            if entity_id:
                edges[entity_id].append(payload)
    return dict(edges)


def load_events(db: Session, selected: list[dict]) -> dict[str, list[dict]]:
    events = db.query(Event).filter(Event.status == "active").order_by(Event.event_date.asc()).all()
    names = [(row["name"], row["name"].lower()) for row in selected if len(row["name"]) >= 3]
    out = defaultdict(list)
    for event in events:
        haystack = f"{event.title} {event.description or ''}".lower()
        for name, needle in names:
            if needle in haystack:
                out[name].append({
                    "title": event.title, "description": event.description or "",
                    "date": event.event_date, "doc_id": event.document_id,
                    "claim": event.canonical_claim_id,
                })
    return dict(out)


def load_documents(db: Session, ids: set[int]) -> dict[int, dict]:
    if not ids:
        return {}
    docs = db.query(Document).filter(Document.id.in_(ids)).all()
    return {
        doc.id: {
            "title": doc.title, "url": doc.url, "source": doc.source_name or domain(doc.url),
            "published": doc.published_at, "domain": domain(doc.url),
        }
        for doc in docs
    }


# --------------------------------------------------------------------------- #
# page rendering
# --------------------------------------------------------------------------- #

def render_article(row: dict, ctx: dict, docs: dict, edges: list[dict],
                   events: list[dict], claims: list[dict], neighbors: dict[str, str],
                   prose: str | None) -> str:
    base = "../"
    refs: dict[int, int] = {}

    def cite(doc_id):
        if not doc_id or doc_id not in docs:
            return ""
        if doc_id not in refs:
            refs[doc_id] = len(refs) + 1
        return f'<sup class="cite"><a href="#ref-{refs[doc_id]}">[{refs[doc_id]}]</a></sup>'

    entity_slugs = ctx["slugs"]

    def linkify(text: str) -> str:
        safe = esc(text)
        for name in sorted(neighbors, key=len, reverse=True):
            slug = entity_slugs.get(name)
            if not slug:
                continue
            pattern = re.compile(r"(?<![\w>])" + re.escape(esc(name)) + r"(?![\w<])", re.I)
            safe = pattern.sub(lambda m: f'<a href="{base}wiki/{slug}.html">{m.group(0)}</a>', safe, count=3)
        return safe

    facts = [c for c in claims if c["status"] in ("active", "disputed")][:30]
    disputed = [c for c in claims if c["status"] == "disputed"]

    related = []
    for name in list(neighbors)[:8]:
        slug = entity_slugs.get(name)
        if slug:
            related.append(f'<a class="chip" href="{base}wiki/{slug}.html">{esc(name)}</a>')

    doc_ids = {c["doc_id"] for c in claims if c["doc_id"]}
    doc_ids |= {e["doc_id"] for e in edges if e["doc_id"]}
    doc_ids |= {e["doc_id"] for e in events if e["doc_id"]}
    sources = sorted(
        {d for d in doc_ids if d in docs},
        key=lambda d: docs[d]["title"].lower(),
    )

    years = sorted({c["published"].year for c in claims if c["published"]})
    year_text = f"{years[0]}–{years[-1]}" if len(years) > 1 else (str(years[0]) if years else "—")

    infobox = f"""<aside class="infobox"><div class="infobox-title">{esc(row['name'])}</div><table>
<tr><th>Type</th><td><a href="{base}category/{esc(row['type'])}.html">{esc(type_label(row['type']))}</a></td></tr>
<tr><th>Knowledge base</th><td>{esc(ctx['kb_label'])}</td></tr>
<tr><th>Mentions</th><td>{len(claims)} claims · {len(events)} events</td></tr>
<tr><th>Connections</th><td>{len(edges)}</td></tr>
<tr><th>Sources</th><td>{len(sources)} documents</td></tr>
<tr><th>Claims recorded</th><td>{esc(year_text)}</td></tr>
<tr><th>Related</th><td>{''.join(related) or '—'}</td></tr>
</table></aside>"""

    lead = prose or (esc(claims[0]["text"]) if claims else esc(row["description"] or ""))
    facts_rows = "".join(
        f"<tr><td>{linkify(c['text'])}{cite(c['doc_id'])}</td>"
        f"<td>{esc(c['actor'])}</td>"
        f"<td class=\"nowrap\">{(c['published'].strftime('%Y-%m-%d') if c['published'] else '—')}</td>"
        f"<td class=\"nowrap\">{int(round((c['confidence'] or 0) * 100))}%</td></tr>"
        for c in facts
    )
    timeline = "".join(
        f'<li><span class="tl-date">{(e["date"].strftime("%Y-%m-%d") if e["date"] else "—")}</span>'
        f'<div class="tl-body"><b>{esc(e["title"])}</b> {linkify(e["description"])}{cite(e["doc_id"])}</div></li>'
        for e in events[:12]
    )
    grouped = defaultdict(list)
    for edge in edges:
        other = edge["target"] if edge["source"].lower() == row["name"].lower() else edge["source"]
        grouped[edge["type"]].append((other, edge))
    connections = ""
    for rel_type, items in list(grouped.items())[:12]:
        lis = []
        for other, edge in items[:6]:
            slug = entity_slugs.get(other)
            label = f'<a href="{base}wiki/{slug}.html">{esc(other)}</a>' if slug else esc(other)
            lis.append(f'<li>{label} — {linkify(edge["description"])}{cite(edge["doc_id"])}</li>')
        connections += f"<h3>{esc(rel_type.replace('_', ' ').title())}</h3><ul class=\"rel-list\">{''.join(lis)}</ul>"

    debates = "".join(
        f'<li><span class="stance stance-disputed">Disputed</span> {linkify(c["text"])}{cite(c["doc_id"])}</li>'
        for c in disputed[:10]
    )
    see_also = "".join(related)
    references = "".join(
        f'<li id="ref-{refs[d]}">{esc(docs[d]["title"])} — {esc(docs[d]["domain"] or docs[d]["source"] or "")}'
        + (f' · {docs[d]["published"].strftime("%Y-%m-%d")}' if docs[d]["published"] else "")
        + (f' <a class="ext" href="{esc(docs[d]["url"])}" rel="nofollow noopener">link</a>' if docs[d]["url"] else "")
        + "</li>"
        for d in sorted(refs, key=lambda x: refs[x])
    )

    sections = []
    if facts_rows:
        sections.append(f'<h2 id="facts">Key facts</h2><table class="facts"><thead><tr><th>Statement</th><th>Actor</th><th>Recorded</th><th>Conf.</th></tr></thead><tbody>{facts_rows}</tbody></table>')
    if timeline:
        sections.append(f'<h2 id="history">History and timeline</h2><ol class="timeline">{timeline}</ol>')
    if connections:
        sections.append(f'<h2 id="connections">Connections</h2>{connections}')
    if debates:
        sections.append(f'<h2 id="debates">Perspectives and debates</h2><ul class="debate-list">{debates}</ul>')
    if see_also:
        sections.append(f'<h2 id="see-also">See also</h2><div class="chips">{see_also}</div>')
    if references:
        sections.append(f'<h2 id="sources">References</h2><ol class="references">{references}</ol>')

    body = (
        f'<div class="article-head"><h1>{esc(row["name"])}</h1>'
        f'<div class="article-sub">From the {esc(ctx["kb_label"])} knowledge base</div></div>'
        f'<div class="article-layout"><article class="prose">{infobox}'
        f'<p class="lead">{lead}</p>'
        + "".join(sections) +
        f'<div class="catlinks"><b>Categories:</b> <a href="{base}category/{esc(row["type"])}.html">{esc(type_label(row["type"]))}</a></div>'
        "</article></div>"
    )
    return shell(f"{row['name']}", ctx["kb_label"], "../", ctx["catalog"], body,
                 asset_base="../../")


def render_index(ctx: dict, selected: list[dict], counts: dict, events: list[dict],
                 docs: list[dict]) -> str:
    base = ""
    stats = "".join(
        f"<div><b>{value:,}</b><span>{esc(label)}</span></div>"
        for label, value in counts.items()
    )
    featured = selected[0] if selected else None
    feature_html = ""
    if featured:
        lead = ctx["prose"].get(featured["name"]) or featured["description"]
        feature_html = (
            f'<section class="feature-card"><div class="kicker">Featured article</div>'
            f'<h2><a href="wiki/{slugify(featured["name"])}.html">{esc(featured["name"])}</a></h2>'
            f'<p>{esc(_plain_markdown(lead))[:400]}</p>'
            f'<a class="more" href="wiki/{slugify(featured["name"])}.html">Read the article →</a></section>'
        )
    cat_cards = ""
    for entity_type in ctx["catalog"]["category_order"]:
        rows = ctx["catalog"]["by_type"][entity_type][:8]
        chips = "".join(
            f'<a class="chip" href="wiki/{slugify(r["name"])}.html">{esc(r["name"])}</a>'
            for r in rows
        )
        cat_cards += (
            f'<div class="cat-card"><a class="cat-name" href="category/{esc(entity_type)}.html">'
            f'{esc(type_label(entity_type))}</a>'
            f'<div class="cat-count">{len(ctx["catalog"]["by_type"][entity_type])} featured</div>'
            f'<div class="chips">{chips}</div></div>'
        )
    recent = "".join(
        f'<li><span class="tl-date">{(e["date"].strftime("%Y-%m-%d") if e["date"] else "—")}</span> '
        f'{esc(e["title"])}</li>'
        for e in sorted(events, key=lambda e: e["date"] or datetime.min)[-8:][::-1]
    )
    src = "".join(
        f'<li><span class="src-name">{esc(d["domain"] or d["source"] or "source")}</span> '
        f'<span class="muted">{esc(d["title"])}</span></li>'
        for d in docs[:12]
    )
    body = f"""
<section class="hero">
  <div class="hero-kicker">Knowledge base · Wikipedia-style portal</div>
  <h1>{esc(ctx['kb_label'])}</h1>
  <p>{esc(ctx['description'])}</p>
  <div class="stats">{stats}</div>
</section>
<div class="portal-grid">
  <div class="portal-main">
    {feature_html}
    <section><h2 class="section-h">Browse by category</h2><div class="cat-grid">{cat_cards}</div></section>
  </div>
  <aside class="portal-side">
    <section><h2 class="section-h">Recent events</h2><ul class="recent-list">{recent}</ul></section>
    <section><h2 class="section-h">Sources</h2><ul class="src-list">{src}</ul></section>
  </aside>
</div>
"""
    return shell("Main page", ctx["kb_label"], "", ctx["catalog"], body,
                 asset_base="../")


def render_all(ctx: dict, selected: list[dict]) -> str:
    groups = defaultdict(list)
    for row in selected:
        letter = (row["name"][0].upper() if row["name"] else "#")
        groups[letter if letter.isalnum() else "#"].append(row)
    body = [f'<div class="article-head"><h1>All articles</h1><div class="article-sub">{len(selected)} entries</div></div>']
    for letter in sorted(groups):
        items = "".join(
            f'<li><a href="wiki/{slugify(r["name"])}.html">{esc(r["name"])}</a> '
            f'<span class="muted">{esc(type_label(r["type"]))}</span></li>'
            for r in sorted(groups[letter], key=lambda r: r["name"].lower())
        )
        body.append(f'<section class="alpha-group"><h2>{esc(letter)}</h2><ul class="alpha-list">{items}</ul></section>')
    return shell("All articles", ctx["kb_label"], "", ctx["catalog"], "".join(body),
                 asset_base="../")


def render_timeline(ctx: dict, events: list[dict], slugs: dict[str, str]) -> str:
    items = []
    for event in sorted(events, key=lambda e: e["date"] or datetime.min, reverse=True):
        link = ""
        for name, slug in slugs.items():
            if len(name) >= 3 and name.lower() in f"{event['title']} {event['description']}".lower():
                link = f' <a class="chip" href="wiki/{slug}.html">{esc(name)}</a>'
                break
        items.append(
            f'<li><span class="tl-date">{(event["date"].strftime("%Y-%m-%d") if event["date"] else "—")}</span>'
            f'<div class="tl-body"><b>{esc(event["title"])}</b> {esc(event["description"])}{link}</div></li>'
        )
    body = (
        f'<div class="article-head"><h1>Timeline</h1>'
        f'<div class="article-sub">{len(events)} events</div></div>'
        f'<ol class="timeline">{"".join(items)}</ol>'
    )
    return shell("Timeline", ctx["kb_label"], "", ctx["catalog"], body,
                 asset_base="../")


def render_category(ctx: dict, entity_type: str, rows: list[dict]) -> str:
    cards = "".join(
        f'<div class="cat-card"><a class="cat-name" href="../wiki/{slugify(r["name"])}.html">{esc(r["name"])}</a>'
        f'<div class="cat-count">{r["degree"]} links · {r["claim_count"]} claims</div>'
        f'<p class="muted">{esc((r["description"] or "")[:160])}</p></div>'
        for r in rows
    )
    body = (
        f'<div class="article-head"><h1>{esc(type_label(entity_type))}</h1>'
        f'<div class="article-sub">{len(rows)} entries</div></div>'
        f'<div class="cat-grid">{cards}</div>'
    )
    return shell(type_label(entity_type), ctx["kb_label"], "../", ctx["catalog"], body,
                 asset_base="../../")


def render_about(ctx: dict, counts: dict) -> str:
    base = ""
    rows = "".join(f"<li><b>{esc(k)}</b>: {v:,}</li>" for k, v in counts.items())
    body = f"""
<div class="article-head"><h1>About this wiki</h1><div class="article-sub">How this portal is built</div></div>
<article class="prose">
<p class="lead">This portal is generated deterministically from the {esc(ctx['kb_label'])} knowledge base. Every statement links back to the document it came from; nothing is authored here.</p>
<h2>Method</h2>
<ul>
  <li><b>Facts</b> — canonical claims (active/disputed), each with page and document citation.</li>
  <li><b>Timeline</b> — events extracted from documents.</li>
  <li><b>Connections</b> — relationships resolved to entities; edge weight = number of distinct documents.</li>
  <li><b>References</b> — source documents for the claims/relations shown on the page.</li>
</ul>
<h2>Corpus</h2>
<ul>{rows}</ul>
<h2>Limitations</h2>
<p class="muted">Claims are model-extracted and may be incomplete. Disputed claims are shown explicitly and never silently resolved. This site is a static snapshot; regenerate it after the knowledge base changes.</p>
</article>
"""
    return shell("About", ctx["kb_label"], "", ctx["catalog"], body,
                 asset_base="../")


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--kb-dir", required=True)
    parser.add_argument("--kb-label", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--min-claims", type=int, default=3)
    parser.add_argument("--assets", default=DEFAULT_ASSETS)
    parser.add_argument("--prose-dir", default=None,
                        help="exports/wiki/pages directory (LLM Wiki prose)")
    args = parser.parse_args()

    out_root = os.path.abspath(args.out_root)
    kb_dir = os.path.join(out_root, args.kb_dir)
    os.makedirs(os.path.join(kb_dir, "wiki"), exist_ok=True)
    os.makedirs(os.path.join(kb_dir, "category"), exist_ok=True)
    os.makedirs(os.path.join(out_root, "assets"), exist_ok=True)
    for asset in ("wiki.css", "wiki.js"):
        src = os.path.join(args.assets, asset)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(out_root, "assets", asset))

    prose: dict[str, str] = {}
    if args.prose_dir and os.path.isdir(args.prose_dir):
        index_path = os.path.join(args.prose_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path, encoding="utf-8") as handle:
                listing = json.load(handle)
            for entry in listing.get("subjects", []):
                subject = entry.get("subject")
                parts = entry.get("pages") or []
                if not subject or not parts:
                    continue
                text = ""
                for part in parts[:1]:
                    path = os.path.join(args.prose_dir, f"{part}.md")
                    if os.path.exists(path):
                        with open(path, encoding="utf-8") as handle:
                            text += "\n" + handle.read()
                if text:
                    prose[subject] = _plain_markdown(text)

    db = SessionLocal()
    started = time.perf_counter()
    try:
        selected, catalog = pick_entities(db, args.limit, args.min_claims)
        claims = load_claims(db, selected)
        edges = load_edges(db, selected)
        events = load_events(db, selected)
        doc_ids = set()
        for items in claims.values():
            doc_ids |= {c["doc_id"] for c in items if c["doc_id"]}
        for items in edges.values():
            doc_ids |= {e["doc_id"] for e in items if e["doc_id"]}
        docs = load_documents(db, doc_ids)

        counts = {
            "documents": db.query(Document).count(),
            "claims": db.query(CanonicalClaim).filter(
                CanonicalClaim.status.in_(["active", "disputed"])).count(),
            "entities": db.query(Entity).filter(Entity.merged_into.is_(None)).count(),
            "relationships": db.query(Relationship).filter(
                Relationship.status == "active").count(),
            "events": db.query(Event).filter(Event.status == "active").count(),
        }
    finally:
        db.close()

    slugs: dict[str, str] = {}
    used_slugs: set[str] = set()
    for row in selected:
        base_slug = slugify(row["name"])
        slug = base_slug
        suffix = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        slugs[row["name"]] = slug
    ctx = {
        "kb_label": args.kb_label, "description": args.description,
        "catalog": catalog, "slugs": slugs,
        "prose": {k: v for k, v in prose.items() if k in slugs},
    }

    pages = 0
    for row in selected:
        neighbors = {}
        for edge in edges.get(row["id"], []):
            other = edge["target"] if edge["source"].lower() == row["name"].lower() else edge["source"]
            if other != row["name"] and other in slugs:
                neighbors[other] = slugs[other]
        html_text = render_article(
            row, ctx, docs, edges.get(row["id"], []), events.get(row["name"], []),
            claims.get(row["name"], []), neighbors, ctx["prose"].get(row["name"]),
        )
        with open(os.path.join(kb_dir, "wiki", f"{slugs[row['name']]}.html"), "w", encoding="utf-8") as handle:
            handle.write(html_text)
        pages += 1

    all_events = []
    db = SessionLocal()
    try:
        for event in db.query(Event).filter(Event.status == "active").order_by(Event.event_date.desc()).limit(500).all():
            all_events.append({"title": event.title, "description": event.description or "",
                               "date": event.event_date})
        doc_list = [
            {"title": d.title, "url": d.url, "source": d.source_name or domain(d.url),
             "published": d.published_at, "domain": domain(d.url)}
            for d in db.query(Document).order_by(Document.collected_at.desc()).limit(40).all()
        ]
    finally:
        db.close()

    with open(os.path.join(kb_dir, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(render_index(ctx, selected, counts, all_events, doc_list))
    with open(os.path.join(kb_dir, "all.html"), "w", encoding="utf-8") as handle:
        handle.write(render_all(ctx, selected))
    with open(os.path.join(kb_dir, "timeline.html"), "w", encoding="utf-8") as handle:
        handle.write(render_timeline(ctx, all_events, slugs))
    with open(os.path.join(kb_dir, "about.html"), "w", encoding="utf-8") as handle:
        handle.write(render_about(ctx, counts))

    for entity_type in catalog["category_order"]:
        with open(os.path.join(kb_dir, "category", f"{entity_type}.html"), "w", encoding="utf-8") as handle:
            handle.write(render_category(ctx, entity_type, catalog["by_type"][entity_type]))

    search_entries = []
    for row in selected:
        lead = ctx["prose"].get(row["name"]) or row["description"]
        search_entries.append({
            "t": row["name"], "y": row["type"],
            "u": f"wiki/{slugs[row['name']]}.html",
            "s": _plain_markdown(lead)[:160],
        })
    with open(os.path.join(kb_dir, "search-index.json"), "w", encoding="utf-8") as handle:
        json.dump(search_entries, handle, ensure_ascii=False)

    report = {
        "ok": True, "kb": args.kb_dir, "pages": pages,
        "categories": len(catalog["category_order"]),
        "selected": len(selected), "counts": counts,
        "out": out_root, "seconds": round(time.perf_counter() - started, 1),
    }
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
