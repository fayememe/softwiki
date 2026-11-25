"""Static wiki portal builder: files, links and unique slugs."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "kb"
    ws.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    from softwiki.source_store.db import SessionLocal, get_engine, init_tables

    try:
        get_engine().dispose()
    except Exception:
        pass
    init_tables()
    db = SessionLocal()
    doc = None
    try:
        from softwiki.source_store.models import (
            CanonicalClaim, Document, Entity, Event, Relationship,
        )

        doc = Document(title="Cortex-M55 TRM", url="https://example.com/m55",
                       source_name="ARM", raw_text="x", cleaned_text="x",
                       hash="h1", published_at=datetime(2024, 1, 1))
        db.add(doc)
        db.flush()
        m55 = Entity(name="Cortex-M55", type="product", description="core")
        helium = Entity(name="Helium", type="feature", description="MVE")
        dup = Entity(name="Cortex M55", type="product", description="dup")
        db.add_all([m55, helium, dup])
        db.flush()
        claim = CanonicalClaim(
            id="cc_1", canonical_key="k1", text="Cortex-M55 supports Helium.",
            actor="ARM", topic="m55", stance="unclear", confidence=0.9,
            status="active", primary_document_id=doc.id, evidence_count=2,
            subject="Cortex-M55", object="Helium",
        )
        db.add(claim)
        db.add(CanonicalClaim(
            id="cc_2", canonical_key="k2", text="Cortex M55 is a variant spelling.",
            actor="ARM", topic="m55", stance="unclear", confidence=0.7,
            status="active", primary_document_id=doc.id, evidence_count=1,
            subject="Cortex M55",
        ))
        db.add(Relationship(
            source_name="Cortex-M55", target_name="Helium", relation_type="supports",
            description="Cortex-M55 supports Helium.", document_id=doc.id,
            confidence=0.9, status="active", source_entity_id=m55.id,
            target_entity_id=helium.id, canonical_claim_id="cc_1", weight=2.0,
            evidence_count=2,
        ))
        db.add(Relationship(
            source_name="Cortex M55", target_name="Helium", relation_type="supports",
            description="Variant spelling.", document_id=doc.id, confidence=0.8,
            status="active", source_entity_id=dup.id, target_entity_id=helium.id,
            canonical_claim_id="cc_2",
        ))
        db.add(Event(title="Cortex-M55 announced", description="Announced in 2020",
                     event_date=datetime(2020, 2, 1), document_id=doc.id,
                     status="active"))
        db.commit()
    finally:
        db.close()
    return ws


def test_build_generates_pages_and_valid_links(workspace, tmp_path):
    out = tmp_path / "wikiweb"
    result = subprocess.run(
        [sys.executable, "scripts/wikiweb_build.py",
         "--out-root", str(out), "--kb-dir", "armkb", "--kb-label", "ARM",
         "--limit", "10", "--min-claims", "1"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "WORKSPACE_DIR": str(workspace)},
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "assets" / "wiki.css").exists()
    assert (out / "armkb" / "index.html").exists()
    assert (out / "armkb" / "about.html").exists()
    assert (out / "armkb" / "timeline.html").exists()
    assert (out / "armkb" / "search-index.json").exists()
    pages = list((out / "armkb" / "wiki").glob("*.html"))
    # "Cortex-M55" and "Cortex M55" slugify to the same base; both must survive.
    assert len(pages) == 3

    html = (out / "armkb" / "wiki" / "cortex-m55.html").read_text(encoding="utf-8")
    assert "Cortex-M55" in html
    assert "supports" in html
    assert "../assets/wiki.css" in (out / "armkb" / "index.html").read_text(encoding="utf-8")
    assert "../../assets/wiki.css" in html
