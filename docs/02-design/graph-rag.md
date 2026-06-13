# Graph-RAG Design

## Dual-Track Architecture

softwiki maintains two parallel graph storage tracks serving different query depths:

| Track | Component | Storage | Query Method | Use Case |
|---|---|---|---|---|
| SQLite compatibility layer | `GraphExtractor` → `Entity`/`Relationship` tables | SQLite (`processed.db`) | `SQL LIKE` fuzzy matching | Lightweight keyword filtering, no graph traversal |
| LightRAG enhancement layer | `LightRAGAdapter` → `LightRAG` | Independent storage (JSON/PostgreSQL) | 6 vector + graph query modes + BFS subgraph traversal | Multi-hop reasoning, entity-centric QA, relationship trend analysis |

The two tracks are independently stored and do not depend on each other. The LightRAG enhancement layer checks credential availability via `has_lightrag_credentials()`, and is **graceful in degradation**: the SQLite layer works fine when credentials are not configured.

---

## SQLite Compatibility Layer

### Entry Point

`softwiki/extraction/graph_extractor.py` → `GraphExtractor.extract_graph()`

### Storage Models

**Entity table** (`softwiki/source_store/models.Entity`):

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK, autoincrement |
| `name` | String(150) | **UNIQUE, NOT NULL** — upsert merge key |
| `type` | String(100) | person / organization / country / concept / location / project |
| `description` | Text | Nullable |

**Relationship table** (`softwiki/source_store/models.Relationship`):

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK, autoincrement |
| `source_name` | String(150) | NOT NULL |
| `target_name` | String(150) | NOT NULL |
| `relation_type` | String(100) | NOT NULL |
| `description` | Text | Nullable |
| `document_id` | Integer | FK → `documents.id` ON DELETE CASCADE |
| `confidence` | Float | default 1.0 |
| `published_at` | DateTime | Nullable |

### Write Logic

**Entity**: `name` field has unique constraint; duplicates are **upserted** (check-then-update description/type). Implemented by `DocumentRepository.create_entity()`.

**Relationship**: **Blind insert** — each extraction does a direct INSERT, no deduplication. Multiple relationship records for the same entity pair from different documents may exist. `document_id` foreign keys back to the Document table.

### Extraction Flow

```
cleaned_text
    │
    ├── [LLM available] LLM extraction ──► JSON parse ──► Entity / Relationship object list
    │
    └── [LLM unavailable] _fallback_extract_graph()
                │
                ├── Regex extract capitalized words (filter prepositions/articles)
                ├── Take top 7 deduplicated candidates as Entity (type="concept")
                └── Co-occurrence relationship rules ──► Relationship (type="associated_with" / "disputes_with" / "member_of")
```

LLM extraction is preferred; falls back to heuristic rules (`_fallback_extract_graph`) on failure.

### Query Method

Only supports **SQL `LIKE`** filtering, no graph traversal:

```sql
-- Filter relationships by keyword in description
SELECT * FROM relationships
WHERE description LIKE '%keyword%'
   OR source_name LIKE '%keyword%'
   OR target_name LIKE '%keyword%';
```

Called by `AnswerEngine.ask()` Layer 3 (Graph) module. Attempts LightRAG query first, **falls back** to SQL LIKE.

---

## LightRAG Enhancement Layer

### Entry Point

`softwiki/graph_rag/adapter.py` → `LightRAGAdapter`

### Initialization

```python
adapter = LightRAGAdapter.get_instance(workspace_dir)
await adapter.initialize()
```

Singleton pattern (per workspace), `get_instance()` returns a shared instance for the same workdir.

### Incremental Insertion

```
ainsert(text)
    │
    ├── 1. Text chunking (chunk_token_size=1200, overlap=100)
    ├── 2. LLM auto-extract entities + relations
    ├── 3. Merge nodes/edges by entity name (incremental graph building)
    ├── 4. Compute embeddings (NanoVectorDB / PGVectorStorage)
    └── 5. Update graph storage (NetworkX / PGGraphStorage)
```

Implemented natively by `LightRAG.ainsert()`. Incremental inserts from the same source document do not create duplicate nodes (graph merge deduplicates by entity name).

`source_id` is prepended to the text as `[Source: <id>]\n`, preserving source traceability.

### 6 Query Modes

Selectable via `LightRAGAdapter.query(question, mode)` `mode` parameter:

| Mode | Retrieval Strategy | Use Case | Implementation |
|---|---|---|---|
| `naive` | Pure vector retrieval (no graph traversal) | Simple QA, no entity-relation reasoning needed | Direct vector similarity top-k |
| `local` | Entity-centric, retrieve entity neighborhood subgraph | "What is X", "What are X's characteristics" | Entity embedding → adjacent edges/nodes |
| `global` | Relation-centric, cross-entity aggregation | Topic trends, "What is each organization's stance on X" | Relation embedding → global aggregation |
| `hybrid` | Local + global combined retrieval | Comprehensive graph QA | Two-path retrieval then merge |
| `mix` | Hybrid + vector chunk context | Best-effort scenarios | hybrid + chunk vector retrieval fusion |
| `bypass` | No retrieval, direct LLM call | Testing, meta-QA | Empty context, pure LLM response |

Default mode is `mix`, default `top_k` is 40.

**Additional tool** — `query_context(question, mode)`: returns retrieved raw context (without LLM synthesis), useful for debugging or external processing.

### BFS Subgraph Traversal

```
LightRAGAdapter.explore(entity_name, max_depth=2, max_nodes=50)
    │
    └── graph_storage.get_knowledge_graph(entity, max_depth, max_nodes)
                │
                └── BFS from {entity}, expand adjacent nodes level by level, up to max_depth
```

Returns a structured dict:

```json
{
  "entity": "EntityName",
  "max_depth": 2,
  "nodes_count": 15,
  "edges_count": 23,
  "nodes": [
    {"id": "...", "labels": ["Entity", "Organization"], "properties": {...}},
    ...
  ],
  "edges": [
    {"id": "...", "type": "cooperates_with", "source": "...", "target": "...", "properties": {...}},
    ...
  ],
  "is_truncated": false
}
```

`is_truncated` indicates whether the max_nodes limit truncated results. Used for frontend hints to narrow the query scope.

### Sync Wrappers

Provides sync interface for non-async contexts such as MCP tools:

| Async | Sync |
|---|---|
| `insert_text()` | `sync_insert_text()` |
| `query()` | `sync_query()` |
| `query_context()` | `sync_query_context()` |
| `explore()` | `sync_explore()` |
| `get_status()` | `sync_get_status()` |

Sync wrappers use `asyncio.new_event_loop()` + `run_until_complete()`, compatible with both existing running loop and new loop scenarios.

---

## Storage Backends

### Default Backend: JSON (Zero Configuration)

| Storage Component | Implementation | On-Disk Files |
|---|---|---|
| KV Storage | `JsonKVStorage` | `kv_store.json` |
| Vector Storage | `NanoVectorDBStorage` | `vdb_entities.json`, `vdb_relationships.json`, `vdb_chunks.json` |
| Graph Storage | `NetworkXStorage` | `graph_chunk_entity_relation.graphml` |
| Doc Status | `JsonDocStatusStorage` | `doc_status.json` |

Storage location: `<workspace>/.softwiki/lightrag/` (resolved by `get_softwiki_dir("lightrag")`).

### PostgreSQL Backend

| Storage Component | Implementation Class |
|---|---|
| KV Storage | `PGKVStorage` |
| Vector Storage | `PGVectorStorage` |
| Graph Storage | `PGGraphStorage` |
| Doc Status | `PGDocStatusStorage` |

### Configuration

```bash
# Default JSON (no configuration needed)
export LIGHTRAG_STORAGE=json

# PostgreSQL
export LIGHTRAG_STORAGE=postgres
export LIGHTRAG_PG_URL=postgresql://user:pass@localhost:5432/softwiki
```

---

## Dimension Safety

When the embedding model changes causing vector dimension mismatch, LightRAG cannot continue using the existing index.

### Check Mechanism

`_check_dimension_mismatch()` executes during `initialize()`:

1. Check if `graph_chunk_entity_relation.graphml` exists (determines if this is an existing data workspace)
2. Read `embedding_dim` from NanoVectorDB storage files (`vdb_entities.json` / `vdb_relationships.json` / `vdb_chunks.json`)
3. Compare with current `LIGHTRAG_EMBED_DIM` or `KNOWN_EMBED_DIMS[model]`
4. On mismatch, print prominent error message (box-drawing border) and raise `RuntimeError`

### Known Model Dimension Table

`KNOWN_EMBED_DIMS` dictionary maps common model dimensions:

| Model | Dimension |
|---|---|
| `text-embedding-3-small` | 1536 |
| `text-embedding-3-large` | 3072 |
| `text-embedding-ada-002` | 1536 |
| `text-embedding-004` | 768 |
| `models/embedding-001` | 768 |
| `deepseek-embedding` | 2048 |
| `bge-m3` | 1024 |
| `bge-small-zh-v1.5` | 512 |
| `all-MiniLM-L6-v2` | 384 |

Models not in the table default to `1536` (OpenAI-compatible), overridable via `LIGHTRAG_EMBED_DIM` environment variable.

### Remediation

```
# Delete LightRAG storage directory, re-ingest all documents
rm -rf <workspace>/.softwiki/lightrag/
```

**Never auto-rebuilds** — users must explicitly delete or revert configuration to avoid silent data corruption.

---

## LLM / Embedding Separation

LLM (entity extraction + query synthesis) and Embedding (vector index) use **completely independent configuration**, can point to different providers:

### LLM Configuration

| Environment Variable | Fallback | Default |
|---|---|---|
| `LIGHTRAG_LLM_API_KEY` | `OPENAI_API_KEY` | `""` |
| `LIGHTRAG_LLM_API_BASE` | `OPENAI_API_BASE` | `https://api.openai.com/v1` |
| `LIGHTRAG_LLM_MODEL` | `EXTRACTION_MODEL` | `gpt-4o-mini` |

### Embedding Configuration

| Environment Variable | Fallback | Default |
|---|---|---|
| `LIGHTRAG_EMBED_API_KEY` | `OPENAI_API_KEY` | `""` |
| `LIGHTRAG_EMBED_API_BASE` | `OPENAI_API_BASE` | `https://api.openai.com/v1` |
| `LIGHTRAG_EMBED_MODEL` | `EMBEDDING_MODEL` | `text-embedding-3-small` |
| `LIGHTRAG_EMBED_PROVIDER` | `EMBEDDING_PROVIDER` | `openai` |
| `LIGHTRAG_EMBED_DIM` | `KNOWN_EMBED_DIMS[model]` | `1536` |

### Separation Example

```bash
# LLM uses OpenAI
export LIGHTRAG_LLM_API_KEY=sk-xxx
export LIGHTRAG_LLM_MODEL=gpt-4o

# Embedding uses local model
export LIGHTRAG_EMBED_PROVIDER=local
export LIGHTRAG_EMBED_DIM=384
```

### Local Embedding Provider

When `provider=local`, uses a character-hash-based zero-dependency embedding:

```python
# Map UTF-32 character code values modulo dim into embedding space
chars = np.frombuffer(text.encode("utf-32", "replace"), dtype=np.uint32)[1:] % dim
embed = np.bincount(chars, minlength=dim).astype(np.float32)
embed = embed / (np.linalg.norm(embed) + 1e-12)
```

No API key needed for deterministic vectors, suitable for development testing or fully local scenarios.

---

## Credential Checking

`has_lightrag_credentials()` controls whether the entire layer activates:

```python
def has_lightrag_credentials() -> bool:
    llm = _llm_config()
    emb = _embed_config()
    llm_ok = bool(llm["api_key"]) and not llm["api_key"].startswith("your_")
    emb_ok = bool(emb["api_key"]) and not emb["api_key"].startswith("your_") or emb["provider"] == "local"
    return llm_ok and emb_ok
```

- `local` provider does not need an API key (emb_ok = True)
- Placeholder keys starting with `your_` are treated as unconfigured
- When credentials are insufficient, `LightRAGAdapter.get_instance()` can still be created, but LLM/Embedding calls during `initialize()` will fail

---

## Status Monitoring

`get_status()` returns LightRAG storage status:

```json
{
  "initialized": true,
  "working_dir": "/path/to/.softwiki/lightrag",
  "graph_nodes": 1423,
  "graph_edges": 5782,
  "graph_error": null
}
```

Used for health checks and operational monitoring. `graph_nodes`/`graph_edges` are read directly from NetworkX graph counts.
