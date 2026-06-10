import os
import threading
import time
import logging
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
        
        extraction_text = cleaned_text[:15000]
        
        # 1. Claim DB Module
        if is_module_enabled("claimdb"):
            extractor = ClaimExtractor()
            claims = extractor.extract_claims(doc_id, extraction_text, published_at)
            for c in claims:
                DocumentRepository.create_claim(db, c)
                
        # 2. Graph Module (SQLite + optional LightRAG)
        if is_module_enabled("graph"):
            graph_extractor = GraphExtractor()
            graph_data = graph_extractor.extract_graph(doc_id, extraction_text, published_at)
            for entity in graph_data["entities"]:
                DocumentRepository.create_entity(db, entity)
            for rel in graph_data["relationships"]:
                DocumentRepository.create_relationship(db, rel)

            # Also insert into LightRAG if available
            lr = _get_lightrag_adapter()
            if lr is not None:
                try:
                    lr.sync_insert_text(extraction_text, source_id=f"doc_{doc_id}")
                    logger.info(f"LightRAG: inserted doc {doc_id}")
                except Exception as lr_err:
                    logger.warning(f"LightRAG insert failed for doc {doc_id}: {lr_err}")
                
        # 3. Timeline Module
        if is_module_enabled("timeline"):
            timeline_extractor = TimelineExtractor()
            events = timeline_extractor.extract_events(doc_id, extraction_text, published_at)
            for ev in events:
                DocumentRepository.create_event(db, ev)
                
        doc.status = "completed"
        db.commit()

        # Stage 4: save extraction artifacts to disk
        try:
            from softwiki.ingestion.file_store import save_extraction
            from softwiki.source_store.document_repo import DocumentRepository as DR
            doc_claims = [c for c in DR.get_all_claims(db) if c.document_id == doc_id]
            doc_rels = [r for r in DR.get_all_relationships(db) if r.document_id == doc_id]
            doc_events = DR.get_events_by_document(db, doc_id)
            doc_entity_names = {r.source_name for r in doc_rels} | {r.target_name for r in doc_rels}
            doc_entities = [e for e in DR.get_all_entities(db) if e.name in doc_entity_names]
            save_extraction(doc_id, doc_claims, doc_entities, doc_rels, doc_events)
        except Exception as fe:
            print(f"[Worker] file_store extraction save failed for doc {doc_id}: {fe}")

        print(f"[Worker] Background extraction completed successfully for Document ID {doc_id}.")
    except Exception as e:
        print(f"[Worker] Background extraction failed for Document ID {doc_id}: {e}")
        try:
            # Re-fetch document using a fresh session query
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
        
    results = {}
    extraction_text = cleaned_text[:15000]
    
    # 1. Claim DB Module
    if is_module_enabled("claimdb"):
        extractor = ClaimExtractor()
        claims = extractor.extract_claims(doc_id, extraction_text, published_at)
        for c in claims:
            DocumentRepository.create_claim(db, c)
        results["claims"] = len(claims)
    else:
        results["claims"] = 0

    # 2. Graph Module (SQLite + optional LightRAG)
    if is_module_enabled("graph"):
        graph_extractor = GraphExtractor()
        graph_data = graph_extractor.extract_graph(doc_id, extraction_text, published_at)
        for entity in graph_data["entities"]:
            DocumentRepository.create_entity(db, entity)
        for rel in graph_data["relationships"]:
            DocumentRepository.create_relationship(db, rel)
        results["entities"] = len(graph_data["entities"])
        results["relationships"] = len(graph_data["relationships"])

        lr = _get_lightrag_adapter()
        if lr is not None:
            try:
                lr.sync_insert_text(extraction_text, source_id=f"doc_{doc_id}")
                logger.info(f"LightRAG: inserted doc {doc_id}")
            except Exception as lr_err:
                logger.warning(f"LightRAG insert failed for doc {doc_id}: {lr_err}")
    else:
        results["entities"] = 0
        results["relationships"] = 0

    # 3. Timeline Module
    if is_module_enabled("timeline"):
        timeline_extractor = TimelineExtractor()
        events = timeline_extractor.extract_events(doc_id, extraction_text, published_at)
        for ev in events:
            DocumentRepository.create_event(db, ev)
        results["events"] = len(events)
    else:
        results["events"] = 0

    if doc:
        doc.status = "completed"
        db.commit()

    # Stage 4: save extraction artifacts to disk
    try:
        from softwiki.ingestion.file_store import save_extraction
        doc_claims = [c for c in DocumentRepository.get_all_claims(db) if c.document_id == doc_id]
        doc_rels = [r for r in DocumentRepository.get_all_relationships(db) if r.document_id == doc_id]
        doc_events = DocumentRepository.get_events_by_document(db, doc_id)
        # Filter entities to those referenced by this document's relationships
        doc_entity_names = {r.source_name for r in doc_rels} | {r.target_name for r in doc_rels}
        all_entities = DocumentRepository.get_all_entities(db)
        doc_entities = [e for e in all_entities if e.name in doc_entity_names]
        save_extraction(doc_id, doc_claims, doc_entities, doc_rels, doc_events)
    except Exception as e:
        pass  # non-fatal, DB is source of truth

    return results
