# Extraction Pipeline

## Five-Stage Pipeline

softwiki decomposes the transformation from raw sources to structured knowledge into five serial stages, each with well-defined inputs/outputs and on-disk locations.

### Stage 1. Ingestion

**Entry**: `softwiki/ingestion/web_loader.py` / `pdf_loader.py`

| Input | Processing | Output |
|---|---|---|
| URL or local PDF path | requests + BeautifulSoup for web scraping, or PyMuPDF for PDF text extraction | raw_text + cleaned_text + metadata (title, author, published_at, language) |

**On disk**: `raw/html/<url_hash>.html` (web raw HTML) or `raw/pdf/<doc_id>_<filename>.pdf` (PDF copy)

**DB**: `Document` record written to processed.db (raw_text, cleaned_text, hash, published_at, etc.).

**Dedup**: `calculate_hash()` computes SHA-256 of cleaned_text; `is_duplicate_hash()` / `is_duplicate_url()` check before insert; hit = skip.

**Scope guard**: `check_scope()` uses LLM to determine if content is within the workspace scope.md topic range; out-of-scope content is skipped.

### Stage 2. Normalize

**Entry**: `softwiki/ingestion/normalize.py`

| Input | Processing | Output |
|---|---|---|
| raw_text from previous stage | `normalize_text()` → `clean_whitespace()` (merge consecutive newlines/spaces) → smart quotes/dashes to ASCII | Clean plain text |

**On disk**: `.softwiki/md/<doc_id>_<slug>.md` — markdown file with metadata header (title, source, language, URL, date).

```
doc_id    : 42
title     : Some Article Title
language  : en
source    : Reuters
url       : https://...
date      : 2025-06-01
============================================================

[cleaned text body...]
```

**Note**: web_loader/pdf_loader internally call normalize_text, so cleaned_text is already normalized. This stage refers to `save_processed_document()` which writes the cleaned text separately for intermediate inspection.

### Stage 3. Chunking

**Entry**: `softwiki/rag/chunker.py`

| Input | Processing | Output |
|---|---|---|
| cleaned_text + metadata | `build_document_chunks()` → paragraph-aware splitting with section tracking, chunk_size=1000, overlap=200 | Structured chunk list with context headers |

Each chunk includes:
- `document_id`, `chunk_index`, `text` (with `[Document: ... | Source: ... | Date: ... | Section: ...]` header)
- `title`, `section`, `published_at`

**On disk**: `.softwiki/chunks/<doc_id>.json` — JSON array of all chunks.

**DB**: `Chunk` records written to processed.db.

**Vector/BM25 incremental update**:
- `LocalVectorStore.add_vectors(chunk_ids, embeddings)` — append per-document to `.softwiki/index/vector_index.npz`
- `Bm25Store.add_documents({cid: text})` — append to `.softwiki/index/bm25_index.pkl` with internal rebuild (BM25 requires full-corpus IDF)

### Stage 4. Extraction

**Entry**: `softwiki/extraction/processor.py`

| Input | Processing | Output |
|---|---|---|
| cleaned_text[:15000] + doc_id + published_at | Run three extractors sequentially per module config: Claim → Graph → Timeline | Structured knowledge records written to DB |

**Three sub-modules** (controlled via `ENABLED_MODULES`, all enabled by default):

1. **Claim DB** — `ClaimExtractor.extract_claims()` → LLM extracts claims (actor, topic, stance, confidence) → `DocumentRepository.create_claim()`
2. **Graph** — `GraphExtractor.extract_graph()` → LLM extracts entities and relationships
   - Entities (name, type, description) → `create_entity()`
   - Relationships (source→target, relation_type, confidence) → `create_relationship()`
   - Optional: sync insert to LightRAG (`LightRAGAdapter.sync_insert_text()`)
3. **Timeline** — `TimelineExtractor.extract_events()` → LLM extracts timeline events (title, description, event_date, topic) → `create_event()`

**Status transition**: `pending → extracting → completed | failed`

### Stage 5. File Store

**Entry**: `softwiki/ingestion/file_store.py`

After extraction, serializes DB structured results as JSON and writes to `.softwiki/extractions/<doc_id>.json`:

```json
{
  "doc_id": 42,
  "claims": [{ "actor": "...", "topic": "...", "stance": "...", ... }],
  "entities": [{ "name": "...", "type": "...", "description": "..." }],
  "relationships": [{ "source": "...", "target": "...", "relation": "...", ... }],
  "events": [{ "title": "...", "description": "...", "event_date": "...", ... }]
}
```

**Note**: The DB is the sole source of truth; disk files are only for pipeline observability and external tool inspection. `save_extraction()` failure does not interrupt the pipeline.

---

## Sync vs Async

`run_extraction_pipeline(db, doc_id, cleaned_text, published_at, background=False)` switches mode via the `background` parameter:

| Mode | Behavior | Use Case |
|---|---|---|
| `background=False` (default) | Synchronously runs all three extraction modules in the current thread, waits for completion, returns result dict | `softwiki ingest --url ...` CLI |
| `background=True` | Sets doc.status = "pending", spawns daemon thread, returns placeholder result immediately | REST API (`/api/ingest/*`), MCP `ingest()` |

### Background Thread Details

```python
t = threading.Thread(target=_bg_extraction_worker, args=(doc_id, cleaned_text, published_at))
t.daemon = True
t.start()
```

- Thread creates its own SQLAlchemy session (`SessionLocal()`), avoiding parent transaction conflicts
- **`time.sleep(0.5)`** — brief delay to ensure parent transaction (Document insert + commit) completes before child thread reads
- Thread catches all exceptions, sets doc.status = "failed" on failure
- Daemon thread does not prevent process exit

### Call Chain

```
CLI:   ingest → run_extraction_pipeline(background=False) → sync wait → output results
API:   ingest_url/file → run_extraction_pipeline(background=True) → return {"extraction": "pending"}
MCP:   ingest() → Stage 1-3 sync execution → Stage 4 background dispatch → return summary
```

---

## Incremental Strategy

### Ingest-Time Indexing

MCP `ingest()` completes chunking and index update during ingestion, no manual `index()` call needed:

1. `build_document_chunks()` → generate chunks
2. `save_chunks()` → write `.softwiki/chunks/<doc_id>.json`
3. `create_chunks()` → DB write
4. `embed_texts()` → generate vectors
5. `LocalVectorStore.add_vectors()` → append to `.softwiki/index/vector_index.npz`
6. `Bm25Store.add_documents()` → append to `.softwiki/index/bm25_index.pkl`

BM25 requires full-corpus IDF, so `add_documents()` internally does a full rebuild (not true incremental), but is externally presented as incremental append.

### Async LLM Extraction

LLM extraction (Stage 4) runs asynchronously in a background daemon thread, not blocking user operations. Users get an immediate response after initiating ingest, with extraction results eventually written to DB and `.softwiki/extractions/`.

### LightRAG Incremental Insertion

`LightRAGAdapter.sync_insert_text()` calls `LightRAG.ainsert()` — LightRAG internally:
1. Re-chunks the text
2. LLM extracts entities and relations
3. Merges nodes/edges by entity name (incremental graph building)
4. Updates vector index

Incremental inserts from the same source document do not create duplicate nodes (guaranteed by LightRAG's graph merge logic).

### index() Command

The `softwiki index` CLI command is currently **full rebuild**:
1. Delete all chunks (`delete_document_chunks()`)
2. Re-chunk all documents
3. Delete old vector/BM25 index files and rebuild

> **Planned**: Future versions will support incremental `index()` mode, only processing documents added/changed since the last index.

### Full Pipeline State Machine

```
ingestion
   │
   ▼
normalize ──► .softwiki/md/
   │
   ▼
chunking ──► .softwiki/chunks/ + vector/BM25 append
   │
   ├── [background=False] ──► synchronous extraction ──► completed
   └── [background=True]  ──► pending → [daemon thread] → extracting → completed|failed
                                    │
                                    ▼
                              .softwiki/extractions/
```

---

## Pipeline File Layout

```
workspace/<ws>/
├── raw/
│   ├── html/<url_hash>.html        ← Stage 1: raw web HTML
│   └── pdf/<doc_id>_<filename>.pdf ← Stage 1: PDF copy
├── .softwiki/
│   ├── md/<doc_id>_<slug>.md       ← Stage 2: cleaned text
│   ├── chunks/<doc_id>.json        ← Stage 3: chunking results
│   ├── extractions/<doc_id>.json   ← Stage 4→5: extraction results (claims/entities/relationships/events)
│   └── index/                      ← Stage 3: search indexes
│       ├── vector_index.npz        ←   FAISS-flat vector index (numpy .npz)
│       └── bm25_index.pkl          ←   BM25 keyword index (pickle)
└── exports/wiki/                   ← Wiki page build output (wiki build command)
```

| Directory | Stage | Format | Written When | Source of Truth |
|---|---|---|---|---|
| `raw/` | 1 Ingestion | HTML / PDF | on ingest | ❌ |
| `.softwiki/md/` | 2 Normalize | Markdown | on ingest | ❌ |
| `.softwiki/chunks/` | 3 Chunking | JSON | on ingest / index | ❌ |
| `.softwiki/extractions/` | 4→5 Extraction | JSON | after extraction | ❌ |
| `.softwiki/index/` | 3 Indexing | .npz / .pkl | on ingest / index | ❌ (rebuildable) |
| `processed.db` | All | SQLite | continuously written | ✅ |
| `exports/wiki/` | Compilation | Markdown | on wiki build | ❌ |

The DB (processed.db) is the sole source of truth; disk files are for auxiliary inspection and debugging.
