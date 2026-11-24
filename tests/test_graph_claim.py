"""Graph x Claim x Wiki joint retrieval (docs/02-design/graph-claim-wiki.md).

These tests pin the behaviour that used to be broken: Chinese questions could not
link to entities, graph context was an unordered LIKE dump, and compiled wiki
pages were only found when the question happened to contain the topic slug.
"""

import json
import os
from datetime import datetime

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    from softwiki.source_store.db import SessionLocal, get_engine, init_tables

    try:
        get_engine().dispose()
    except Exception:
        pass
    init_tables()
    session = SessionLocal()
    yield session
    session.close()
    try:
        get_engine().dispose()
    except Exception:
        pass


def _doc(db, title, page=None):
    from softwiki.source_store.models import Document

    doc = Document(
        title=title,
        source_name="ARM",
        source_type="manual",
        raw_text=title,
        cleaned_text=title,
        hash=f"hash-{title}",
        published_at=datetime(2024, 1, 1),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _entity(db, name, type_="concept"):
    from softwiki.source_store.models import Entity

    ent = Entity(name=name, type=type_, description=f"{name} description")
    db.add(ent)
    db.commit()
    return ent


def _rel(db, doc, source, target, rtype="implements", conf=0.9, canonical=None):
    from softwiki.source_store.models import Relationship

    rel = Relationship(
        source_name=source,
        target_name=target,
        relation_type=rtype,
        description=f"{source} {rtype} {target}",
        document_id=doc.id,
        confidence=conf,
        canonical_claim_id=canonical,
        status="active",
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def _canonical(db, cid, text, subject=None, object_=None, status="active",
               conf=0.8, evidence=2, doc=None, pages=(3, 4)):
    from softwiki.source_store.models import CanonicalClaim

    claim = CanonicalClaim(
        id=cid,
        canonical_key=f"key-{cid}",
        text=text,
        actor="ARM",
        topic="cortex-m55",
        stance="unclear",
        confidence=conf,
        status=status,
        evidence_count=evidence,
        subject=subject,
        object=object_,
        primary_document_id=doc.id if doc else None,
        primary_page_start=pages[0] if pages else None,
        primary_page_end=pages[1] if pages else None,
    )
    db.add(claim)
    db.commit()
    return claim


def _seed_graph(db):
    doc = _doc(db, "Cortex-M55 Technical Reference Manual")
    _entity(db, "Cortex-M55")
    _entity(db, "Helium")
    _entity(db, "DSP")
    # M55 -> Helium (1 hop), Helium -> DSP (2 hops)
    _rel(db, doc, "Cortex-M55", "Helium", "supports", 0.95, canonical="cc_m55_helium")
    _rel(db, doc, "Helium", "DSP", "enables", 0.60)
    _canonical(db, "cc_m55_helium", "Cortex-M55 supports Helium vector extensions.",
               subject="Cortex-M55", object_="Helium", status="active",
               conf=0.9, evidence=3, doc=doc)
    _canonical(db, "cc_m55_power", "Cortex-M55 has low power modes.",
               subject="Cortex-M55", object_="low power", status="disputed",
               conf=0.7, evidence=1, doc=doc)
    _canonical(db, "cc_m55_error", "Cortex-M55 is wrong.", subject="Cortex-M55",
               status="error", conf=0.9, evidence=5, doc=doc)
    return doc


# --------------------------------------------------------------------------- #
# Terms / entity linking
# --------------------------------------------------------------------------- #

def test_query_terms_extracts_chinese_ngrams():
    from softwiki.intelligence.graph_claim import query_terms

    terms = query_terms("ARM处理器有哪些低功耗特性")
    assert "低功耗" in terms
    assert "处理器" in terms
    assert all(len(t) >= 2 for t in terms)


def test_link_entities_chinese_question(db):
    from softwiki.intelligence.graph_claim import link_entities

    _seed_graph(db)
    seeds = link_entities(db, "Cortex-M55 支持哪些低功耗特性？")
    names = [s["name"] for s in seeds]
    assert "Cortex-M55" in names


def test_link_entities_is_case_and_punctuation_insensitive(db):
    from softwiki.intelligence.graph_claim import link_entities

    _seed_graph(db)
    seeds = link_entities(db, "what does cortex m55 support?")
    assert "Cortex-M55" in [s["name"] for s in seeds]


def test_link_entities_returns_empty_without_match(db):
    from softwiki.intelligence.graph_claim import link_entities

    _seed_graph(db)
    assert link_entities(db, "quantum chromodynamics lattice") == []


# --------------------------------------------------------------------------- #
# Expansion
# --------------------------------------------------------------------------- #

def test_expand_walks_two_hops(db):
    from softwiki.intelligence.graph_claim import expand, link_entities

    _seed_graph(db)
    seeds = link_entities(db, "Cortex-M55")
    edges = expand(db, seeds, max_hops=2)
    hops = {(e["source"], e["target"]): e["hop"] for e in edges}
    assert hops[("Cortex-M55", "Helium")] == 1
    assert hops[("Helium", "DSP")] == 2


# --------------------------------------------------------------------------- #
# Claim attachment / ranking / status
# --------------------------------------------------------------------------- #

def test_retrieve_attaches_and_ranks_claims(db):
    from softwiki.intelligence.graph_claim import retrieve

    _seed_graph(db)
    result = retrieve(db, "Cortex-M55 支持哪些扩展？")

    assert result["seeds"], "expected at least one linked entity"
    assert result["edges"], "expected graph edges"

    ids = [item["claim"].id for item in result["claims"]]
    assert "cc_m55_helium" in ids
    assert "cc_m55_power" in ids            # disputed still participates
    assert "cc_m55_error" not in ids        # error/superseded is excluded

    # Edge-linked claim (hop 1, high confidence) outranks the seed-only claim.
    assert ids.index("cc_m55_helium") < ids.index("cc_m55_power")
    top = result["claims"][0]
    assert top["claim"].primary_page_start == 3


def test_retrieve_returns_empty_without_entities(db):
    from softwiki.intelligence.graph_claim import retrieve

    _seed_graph(db)
    assert retrieve(db, "quantum chromodynamics") == {
        "seeds": [], "edges": [], "claims": [], "raw_claims": [], "wiki": [],
    }


def test_format_graph_context_has_hop_and_citation(db):
    from softwiki.intelligence.graph_claim import format_graph_context, retrieve

    _seed_graph(db)
    result = retrieve(db, "Cortex-M55")
    lines = format_graph_context(result, cite=lambda doc_id: 7)
    assert lines
    assert "hop 1" in lines[0]
    assert lines[0].startswith("- [7] ")


# --------------------------------------------------------------------------- #
# Wiki layer
# --------------------------------------------------------------------------- #

def _write_wiki_page(db, subject, slug, content):
    from softwiki.config import get_export_dir

    out_dir = get_export_dir("wiki/pages")
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"subjects": [{
            "subject": subject,
            "slug": slug,
            "claims_total": 3,
            "claims_covered": 3,
            "pages": [slug],
            "updated_at": "2024-01-01T00:00:00",
        }]}, f)
    with open(os.path.join(out_dir, f"{slug}.md"), "w", encoding="utf-8") as f:
        f.write(content)


def test_retrieve_includes_fresh_wiki_page(db):
    from softwiki.intelligence.graph_claim import retrieve

    _seed_graph(db)
    _write_wiki_page(db, "Cortex-M55", "cortex-m55", "M55 is a small core. [1]")

    result = retrieve(db, "Cortex-M55 是什么？")
    assert [p["subject"] for p in result["wiki"]] == ["Cortex-M55"]


def test_retrieve_skips_stale_wiki_page(db):
    from softwiki.intelligence.graph_claim import retrieve
    from softwiki.source_store.models import WikiArtifactState

    _seed_graph(db)
    _write_wiki_page(db, "Cortex-M55", "cortex-m55", "outdated")
    db.add(WikiArtifactState(topic="Cortex-M55", stale_at=datetime(2024, 2, 1)))
    db.commit()

    result = retrieve(db, "Cortex-M55 是什么？")
    assert result["wiki"] == []


def test_degree_uses_canonical_key_not_raw_name(db):
    """Entity keys come from graph.resolution (strips ', Inc.'); degrees must too."""
    from softwiki.intelligence.graph_claim import link_entities

    doc = _doc(db, "AeroPress manual")
    ent = _entity(db, "AeroPress, Inc.", type_="organization")
    ent.normalized_name = "aeropress"
    db.commit()
    for _ in range(3):
        _rel(db, doc, "AeroPress, Inc.", "Espresso", rtype="related-to")

    seeds = link_entities(db, "AeroPress")
    assert seeds, "entity should link from the plain name"
    assert seeds[0]["entity_id"] == ent.id
    assert seeds[0]["degree"] == 3
