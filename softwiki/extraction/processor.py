import os
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from datetime import datetime
from softwiki.config import is_module_enabled
from softwiki.source_store.models import Document
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.extraction.claim_extractor import ClaimExtractor
from softwiki.extraction.graph_extractor import GraphExtractor
from softwiki.extraction.timeline_extractor import TimelineExtractor

logger = logging.getLogger(__name__)

# Optional LightRAG integration
_lightrag_adapter = None

_lightrag_adapter_warned = False

def _get_lightrag_adapter():
    """Lazy-import and return the LightRAG adapter if available."""
    global _lightrag_adapter, _lightrag_adapter_warned
    if _lightrag_adapter is not None:
        return _lightrag_adapter
    try:
        from softwiki.graph_rag.adapter import LightRAGAdapter, has_lightrag_credentials
        if not has_lightrag_credentials():
            if not _lightrag_adapter_warned:
                logger.warning("LightRAG disabled: no valid API key configured (graph module degrades to SQLite-only)")
                _lightrag_adapter_warned = True
            return None
        _lightrag_adapter = LightRAGAdapter.get_instance()
        return _lightrag_adapter
    except ImportError:
        if not _lightrag_adapter_warned:
            logger.warning("LightRAG not installed (install with: pip install lightrag-hku). Graph query degrades to SQLite-only.")
            _lightrag_adapter_warned = True
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize LightRAG adapter: {e}")
        return None

def _extraction_windows(text: str) -> list:
    window_chars = int(os.getenv("EXTRACTION_WINDOW_CHARS", "12000"))
    overlap = int(os.getenv("EXTRACTION_WINDOW_OVERLAP", "1000"))
    max_windows = max(1, int(os.getenv("EXTRACTION_MAX_WINDOWS", "8")))
    if not text:
        return []
    if len(text) <= window_chars:
        return [text]
    overlap = max(0, min(overlap, window_chars // 4))
    stride = max(1, window_chars - overlap)
    total = max(1, (len(text) - overlap + stride - 1) // stride)
    if total <= max_windows:
        starts = [i * stride for i in range(total)]
    elif max_windows == 1:
        starts = [0]
    else:
        starts = [
            round(i * (len(text) - window_chars) / (max_windows - 1))
            for i in range(max_windows)
        ]
    return [text[start:start + window_chars] for start in starts]


def _extract_document(db, doc_id: int, cleaned_text: str, published_at: datetime) -> dict:
    windows = _extraction_windows(cleaned_text)
    results = {"claims": 0, "entities": 0, "relationships": 0, "events": 0}
    claim_extractor = ClaimExtractor() if is_module_enabled("claimdb") else None
    graph_extractor = GraphExtractor() if is_module_enabled("graph") else None
    timeline_extractor = TimelineExtractor() if is_module_enabled("timeline") else None

    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, window in enumerate(windows):
            claim_future = graph_future = timeline_future = None
            if claim_extractor:
                claim_future = pool.submit(
                    claim_extractor.extract_claims, doc_id, window, published_at
                )
            if graph_extractor:
                graph_future = pool.submit(
                    graph_extractor.extract_graph, doc_id, window, published_at
                )
            if timeline_extractor:
                timeline_future = pool.submit(
                    timeline_extractor.extract_events, doc_id, window, published_at
                )

            claims = claim_future.result() if claim_future else []
            graph_data = graph_future.result() if graph_future else {
                "entities": [], "relationships": []
            }
            events = timeline_future.result() if timeline_future else []

            for claim in claims:
                DocumentRepository.create_claim(db, claim)
            results["claims"] += len(claims)

            for entity in graph_data["entities"]:
                DocumentRepository.create_entity(db, entity)
            for relationship in graph_data["relationships"]:
                DocumentRepository.create_relationship(db, relationship)
            results["entities"] += len(graph_data["entities"])
            results["relationships"] += len(graph_data["relationships"])

            lightrag = _get_lightrag_adapter()
            if graph_extractor and lightrag is not None:
                try:
                    lightrag.sync_insert_text(window, source_id=f"doc_{doc_id}_w{index}")
                except Exception as exc:
                    logger.warning(
                        f"LightRAG insert failed for doc {doc_id} window {index}: {exc}"
                    )

            for event in events:
                DocumentRepository.create_event(db, event)
            results["events"] += len(events)

    return results


def _save_extraction_artifacts(db, doc_id: int) -> None:
    try:
        from softwiki.ingestion.file_store import save_extraction
        doc_claims = [
            claim for claim in DocumentRepository.get_all_claims(db)
            if claim.document_id == doc_id
        ]
        doc_relationships = DocumentRepository.get_relationships_by_document(db, doc_id)
        doc_events = DocumentRepository.get_events_by_document(db, doc_id)
        entity_names = {rel.source_name for rel in doc_relationships}
        entity_names |= {rel.target_name for rel in doc_relationships}
        doc_entities = [
            entity for entity in DocumentRepository.get_all_entities(db)
            if entity.name in entity_names
        ]
        save_extraction(doc_id, doc_claims, doc_entities, doc_relationships, doc_events)
    except Exception as exc:
        logger.warning(f"Extraction artifact save failed for doc {doc_id}: {exc}")


def _bg_extraction_worker(doc_id: int, cleaned_text: str, published_at: datetime):
    """Background thread worker to perform NLP extraction on a document."""
    from softwiki.source_store.db import SessionLocal
    
    # Tiny delay to ensure parent transaction committing completes
    time.sleep(0.5)
    
    db = SessionLocal()
    try:
        doc = DocumentRepository.get_document(db, doc_id)
        if not doc:
            print(f"[Worker] Document ID {doc_id} not found in database.")
            return
        
        doc.status = "extracting"
        db.commit()
        print(f"[Worker] Starting background extraction for Document ID {doc_id}...")

        _extract_document(db, doc_id, cleaned_text, published_at)
        try:
            from softwiki.knowledge.canonical import canonicalize_document
            canonicalize_document(db, doc_id)
        except Exception as exc:
            logger.warning(f"Knowledge canonicalization failed for doc {doc_id}: {exc}")

        doc = DocumentRepository.get_document(db, doc_id)
        if doc:
            doc.status = "completed"
            db.commit()
        _save_extraction_artifacts(db, doc_id)

        print(f"[Worker] Background extraction completed successfully for Document ID {doc_id}.")
    except Exception as e:
        print(f"[Worker] Background extraction failed for Document ID {doc_id}: {e}")
        try:
            db.rollback()
            doc = DocumentRepository.get_document(db, doc_id)
            if doc:
                doc.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def run_extraction_pipeline(db: Session, doc_id: int, cleaned_text: str, published_at: datetime, background: bool = False) -> dict:
    """Executes claim, graph and timeline extractions for a newly ingested document,
    respecting module configuration.
    
    If background=True, sets status to 'pending', spawns a background thread to do the work,
    and returns immediately.
    """
    if background:
        doc = DocumentRepository.get_document(db, doc_id)
        if doc:
            doc.status = "pending"
            db.commit()
        
        # Spawn background thread
        t = threading.Thread(target=_bg_extraction_worker, args=(doc_id, cleaned_text, published_at))
        t.daemon = True
        t.start()
        
        # Return instant placeholder results
        return {
            "status": "pending",
            "claims": 0,
            "entities": 0,
            "relationships": 0,
            "events": 0
        }

    # Otherwise, run synchronously
    doc = DocumentRepository.get_document(db, doc_id)
    if doc:
        doc.status = "extracting"
        db.commit()
        
    results = _extract_document(db, doc_id, cleaned_text, published_at)
    try:
        from softwiki.knowledge.canonical import canonicalize_document
        canonicalize_document(db, doc_id)
    except Exception as exc:
        logger.warning(f"Knowledge canonicalization failed for doc {doc_id}: {exc}")

    doc = DocumentRepository.get_document(db, doc_id)
    if doc:
        doc.status = "completed"
        db.commit()
    _save_extraction_artifacts(db, doc_id)

    return results
