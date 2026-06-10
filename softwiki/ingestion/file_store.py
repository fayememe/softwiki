"""
file_store.py
=============
Saves pipeline artifacts to disk so every stage of the ingestion pipeline
is visible as real files in the workspace directory.

Stage layout inside workspace/:
  raw/html/<url_hash>.html          — original fetched HTML
  raw/pdf/<doc_id>_<filename>.pdf   — original PDF (copy)
  processed/documents/<doc_id>_<slug>.txt    — cleaned document text
  processed/chunks/<doc_id>.json             — all chunks for one document
  processed/extractions/<doc_id>.json        — claims + entities + events

None of these are the source of truth (that's processed.db).
They exist purely to make the pipeline inspectable.
"""

import json
import os
import re
import shutil
from datetime import datetime
from typing import Any

from softwiki.config import get_raw_dir, get_processed_dir


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:max_len] or "doc"


# ---------------------------------------------------------------------------
# Stage 1 — raw/
# ---------------------------------------------------------------------------

def save_raw_html(url_hash: str, raw_html: str) -> str:
    """Save fetched HTML to raw/html/<url_hash>.html. Returns path."""
    path = os.path.join(get_raw_dir("html"), f"{url_hash}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw_html)
    return path


def save_raw_pdf(doc_id: int, src_path: str) -> str:
    """Copy original PDF to raw/pdf/<doc_id>_<filename>.pdf. Returns path."""
    filename = os.path.basename(src_path)
    dst = os.path.join(get_raw_dir("pdf"), f"{doc_id}_{filename}")
    if src_path != dst and os.path.exists(src_path):
        shutil.copy2(src_path, dst)
    return dst


# ---------------------------------------------------------------------------
# Stage 2 — processed/documents/
# ---------------------------------------------------------------------------

def save_processed_document(doc_id: int, title: str, cleaned_text: str,
                             language: str = "en",
                             published_at: Any = None,
                             source_name: str = "",
                             url: str = "") -> str:
    """Save cleaned document text with a metadata header. Returns path."""
    slug = _slug(title)
    path = os.path.join(get_processed_dir("md"), f"{doc_id}_{slug}.md")

    date_str = ""
    if isinstance(published_at, datetime):
        date_str = published_at.strftime("%Y-%m-%d")
    elif isinstance(published_at, str):
        date_str = published_at[:10]

    header = (
        f"doc_id    : {doc_id}\n"
        f"title     : {title}\n"
        f"language  : {language}\n"
        f"source    : {source_name}\n"
        f"url       : {url or 'local'}\n"
        f"date      : {date_str}\n"
        f"{'='*60}\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + cleaned_text)
    return path


# ---------------------------------------------------------------------------
# Stage 3 — processed/chunks/
# ---------------------------------------------------------------------------

def save_chunks(doc_id: int, chunks_data: list) -> str:
    """Save all chunks for one document as JSON. Returns path."""
    path = os.path.join(get_processed_dir("chunks"), f"{doc_id}.json")
    serializable = []
    for c in chunks_data:
        entry = dict(c)
        if isinstance(entry.get("published_at"), datetime):
            entry["published_at"] = entry["published_at"].isoformat()
        serializable.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------------------
# Stage 4 — processed/extractions/
# ---------------------------------------------------------------------------

def save_extraction(doc_id: int,
                    claims: list,
                    entities: list,
                    relationships: list,
                    events: list) -> str:
    """Save extraction results (claims/entities/relationships/events) as JSON. Returns path."""
    path = os.path.join(get_processed_dir("extractions"), f"{doc_id}.json")

    def _claim(c):
        return {
            "id": c.id, "actor": c.actor, "topic": c.topic,
            "stance": c.stance, "confidence": c.confidence,
            "text": c.text,
            "published_at": c.published_at.isoformat() if c.published_at else None,
        }

    def _entity(e):
        return {"name": e.name, "type": e.type, "description": e.description}

    def _rel(r):
        return {
            "source": r.source_name, "target": r.target_name,
            "relation": r.relation_type, "description": r.description,
            "confidence": r.confidence,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }

    def _event(e):
        return {
            "title": e.title, "description": e.description,
            "topic": e.topic, "confidence": e.confidence,
            "event_date": e.event_date.isoformat() if e.event_date else None,
        }

    payload = {
        "doc_id": doc_id,
        "claims": [_claim(c) for c in claims],
        "entities": [_entity(e) for e in entities],
        "relationships": [_rel(r) for r in relationships],
        "events": [_event(e) for e in events],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
