#!/usr/bin/env python3
"""Second-pass graph extraction for documents whose windows hit gateway 5xx.

The bulk re-extraction records ``API graph extraction failed for doc <id>`` when
a window could not be extracted after retries. This script re-runs *only* the
graph extractor for those documents (claims/events untouched), with low
concurrency so the gateway stops answering 504.

Usage:
    python scripts/graph_topup.py --from-log /tmp/reextract.log --workers 2
    python scripts/graph_topup.py --docs 12,19,31 --workers 2
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from softwiki.extraction.graph_extractor import GraphExtractor
from softwiki.extraction.processor import _extraction_windows
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.source_store.models import Document, Relationship

_FAIL_RE = re.compile(r"graph extraction failed for doc (\d+)")


def _docs_from_log(path: str) -> list[int]:
    with open(path, encoding="utf-8", errors="ignore") as handle:
        return sorted({int(m.group(1)) for m in _FAIL_RE.finditer(handle.read())})


def _extract_graph_only(doc_id: int) -> dict:
    started = time.time()
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc is None:
            return {"doc": doc_id, "error": "not found"}
        db.query(Relationship).filter(Relationship.document_id == doc_id).delete()
        db.commit()

        extractor = GraphExtractor()
        windows = _extraction_windows(doc.cleaned_text)
        entities = relationships = 0
        for window in windows:
            data = extractor.extract_graph(doc_id, window, doc.published_at)
            for entity in data.get("entities", []):
                DocumentRepository.create_entity(db, entity)
            for rel in data.get("relationships", []):
                DocumentRepository.create_relationship(db, rel)
            entities += len(data.get("entities", []))
            relationships += len(data.get("relationships", []))
        db.commit()
        return {
            "doc": doc_id,
            "windows": len(windows),
            "entities": entities,
            "relationships": relationships,
            "seconds": round(time.time() - started, 1),
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"doc": doc_id, "error": str(exc)}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default="")
    parser.add_argument("--from-log", default="")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    doc_ids: list[int] = []
    if args.docs:
        doc_ids = [int(value) for value in args.docs.split(",") if value.strip()]
    if args.from_log:
        doc_ids += _docs_from_log(args.from_log)
    doc_ids = sorted(set(doc_ids))
    if not doc_ids:
        print("no documents to top up")
        return

    init_tables()
    print(f"top-up graph for {len(doc_ids)} documents (workers={args.workers})", flush=True)
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_extract_graph_only, doc_id) for doc_id in doc_ids]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result.get("error"):
                failures.append(result)
            print(f"[{index}/{len(doc_ids)}] {result}", flush=True)
    print(f"done, failures={len(failures)}", flush=True)


if __name__ == "__main__":
    main()
