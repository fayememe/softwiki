#!/usr/bin/env python3
"""Deterministic graph normalization for schema v3.

What it does (idempotent):

1. fills entities.normalized_name;
2. merges entities whose normalized names collide (keeps the highest-degree
   row, records the rest as aliases with merged_into pointing at the canonical);
3. materializes explicit extraction aliases into entity_aliases;
4. resolves relationships.source_entity_id / target_entity_id through the
   alias table (falls back to name matching);
5. recomputes per-edge weight / evidence_count across documents.

No rows are deleted: merged entities stay addressable through merged_into and
entity_aliases, relationships keep their document ids for citations.

Usage:
    python scripts/graph_normalize.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.graph.resolution import normalize_entity_name, parse_aliases
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Entity, EntityAlias, Relationship


def _degrees(db) -> dict[str, int]:
    degrees: dict[str, int] = defaultdict(int)
    for source, target in db.query(Relationship.source_name, Relationship.target_name).filter(
        Relationship.status == "active"
    ):
        degrees[normalize_entity_name(source)] += 1
        degrees[normalize_entity_name(target)] += 1
    return degrees


def normalize(db, dry_run: bool = False) -> dict:
    entities = db.query(Entity).all()

    # 1. normalized names
    for entity in entities:
        key = normalize_entity_name(entity.name)
        if entity.normalized_name != key:
            entity.normalized_name = key
    if not dry_run:
        db.flush()

    degrees = _degrees(db)

    # 2. merge exact normalized duplicates
    groups: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        if entity.merged_into:
            continue
        groups[entity.normalized_name or normalize_entity_name(entity.name)].append(entity)

    merged = 0
    alias_rows: dict[tuple[str, int], EntityAlias] = {}
    for key, rows in groups.items():
        if len(rows) == 1:
            continue
        rows.sort(
            key=lambda e: (degrees.get(key, 0), len(e.name), -(e.id or 0)),
            reverse=True,
        )
        canonical = rows[0]
        for duplicate in rows[1:]:
            duplicate.merged_into = canonical.id
            merged += 1
            for alias in {duplicate.name, *parse_aliases(duplicate.aliases)}:
                norm = normalize_entity_name(alias)
                if norm and norm != key:
                    alias_rows[(norm, canonical.id)] = EntityAlias(
                        entity_id=canonical.id, alias=alias[:200], normalized=norm[:200]
                    )
    if not dry_run:
        db.flush()

    # 3. explicit extraction aliases
    alias_added = 0
    existing = {
        (row.normalized, row.entity_id) for row in db.query(EntityAlias).all()
    }
    for entity in entities:
        if entity.merged_into:
            continue
        for alias in parse_aliases(entity.aliases):
            norm = normalize_entity_name(alias)
            if not norm or (norm, entity.id) in existing:
                continue
            existing.add((norm, entity.id))
            alias_rows[(norm, entity.id)] = EntityAlias(
                entity_id=entity.id, alias=alias[:200], normalized=norm[:200]
            )
    for row in alias_rows.values():
        db.add(row)
        alias_added += 1
    if not dry_run:
        db.flush()

    # 4. resolve relationship endpoints
    alias_map: dict[str, int] = {}
    for entity in entities:
        if entity.merged_into:
            continue
        alias_map[entity.normalized_name or normalize_entity_name(entity.name)] = entity.id
    for row in db.query(EntityAlias).all():
        alias_map.setdefault(row.normalized, row.entity_id)

    unresolved = 0
    resolved = 0
    for rel in db.query(Relationship).all():
        src = alias_map.get(normalize_entity_name(rel.source_name))
        tgt = alias_map.get(normalize_entity_name(rel.target_name))
        if src is None or tgt is None:
            unresolved += 1
            continue
        rel.source_entity_id = src
        rel.target_entity_id = tgt
        resolved += 1
    if not dry_run:
        db.flush()

    # 5. edge weight across documents
    stats: dict[tuple[int, int, str], tuple[int, int]] = {}
    for rel in db.query(Relationship).filter(Relationship.status == "active").all():
        if rel.source_entity_id is None or rel.target_entity_id is None:
            continue
        key = (rel.source_entity_id, rel.target_entity_id, rel.relation_type)
        docs, count = stats.get(key, (0, 0))
        stats[key] = (docs + 1, count + 1)  # docs approximated by rows; refined below

    # refine: distinct document count per key
    doc_sets: dict[tuple[int, int, str], set[int]] = defaultdict(set)
    for rel in db.query(Relationship).filter(Relationship.status == "active").all():
        if rel.source_entity_id is None or rel.target_entity_id is None:
            continue
        doc_sets[(rel.source_entity_id, rel.target_entity_id, rel.relation_type)].add(rel.document_id)
    for key, docs in doc_sets.items():
        stats[key] = (len(docs), stats.get(key, (0, 0))[1])

    if not dry_run:
        for rel in db.query(Relationship).all():
            if rel.source_entity_id is None or rel.target_entity_id is None:
                continue
            key = (rel.source_entity_id, rel.target_entity_id, rel.relation_type)
            docs, count = stats.get(key, (1, 1))
            rel.weight = float(docs)
            rel.evidence_count = int(count)
        db.commit()

    return {
        "entities": len(entities),
        "merged": merged,
        "aliases_added": alias_added,
        "relationships_resolved": resolved,
        "relationships_unresolved": unresolved,
        "edge_groups": len(stats),
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    init_tables()
    db = SessionLocal()
    try:
        print(json.dumps(normalize(db, dry_run=args.dry_run), ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
