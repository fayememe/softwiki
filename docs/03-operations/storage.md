# Storage Architecture

> **Scope**: Layout and configuration of all softwiki storage layers: workspace filesystem, SQLite database, LightRAG storage, and optional PostgreSQL backend.
> **Audience**: Operators who need to understand data disk locations and storage structure.

---

## Workspace Filesystem

Each workspace is an independent directory containing all its data, configuration, and output. The path is controlled by the `WORKSPACE_DIR` environment variable, defaulting to `workspace/default`.

```
workspace/<name>/
├── raw/                        # Raw files
│   ├── html/                   #   Raw HTML (fetched)
│   ├── pdf/                    #   Raw PDF (copy)
│   ├── markdown/               #   Raw Markdown
│   └── api/                    #   API response snapshots
│
├── .softwiki/                  # softwiki internal data
│   ├── processed.db            #   SQLite database (primary storage)
│   ├── md/                     #   Cleaned text (.md, human-readable)
│   ├── chunks/                 #   Chunk JSON (one file per document)
│   ├── extractions/            #   LLM extraction results (claims/entities/relationships/events)
│   ├── documents/              #   Document intermediate data
│   ├── embeddings/             #   Embedding vector cache
│   ├── index/                  #   Search indexes (FAISS vector + BM25 keyword)
│   └── lightrag/               #   LightRAG independent storage (see below)
│
├── config/                     # Workspace configuration
│   ├── sources.yaml            #   Data source definitions
│   ├── model_profiles.yaml     #   LLM model configuration
│   ├── scope.md                #   Research scope definition
│   ├── agents.md               #   Custom agent soul (optional)
│   └── workflows.yaml          #   Custom workflow overrides (optional)
│
├── exports/                    # Export output
│   └── wiki/                   #   Wiki page output
│       ├── countries/
│       ├── organizations/
│       ├── topics/
│       ├── events/
│       ├── claims/
│       └── reports/
│
└── .softwiki.yml               # Workspace metadata (optional)
```

> **Note**: Pipeline artifacts in `raw/` and `.softwiki/` serve only as checkpoints for human review; **they are not data sources of truth**. The authoritative source for all persistent data is `.softwiki/processed.db`.

---

## SQLite

### Database

- **Path**: `{WORKSPACE_DIR}/.softwiki/processed.db`
- **Connection URL** (SQLAlchemy): `sqlite:///{WORKSPACE_DIR}/.softwiki/processed.db`
- **ORM**: SQLAlchemy (`Base` in `softwiki/source_store/db.py`)

### Tables

| Table Name | Model Class | Purpose |
|---|---|---|
| `sources` | `SourceConfig` | Predefined data source configuration (name, type, URL, trust level) |
| `documents` | `Document` | Ingested document metadata and full text (title, url, raw_text, cleaned_text, hash) |
| `chunks` | `Chunk` | Document chunks (text, section, chunk_index), FK → documents |
| `claims` | `Claim` | LLM-extracted claims (actor, topic, stance, confidence), FK → documents |
| `entities` | `Entity` | Knowledge graph entities (name, type, description), globally unique |
| `relationships` | `Relationship` | Entity relationships (source_name, target_name, relation_type), FK → documents |
| `events` | `Event` | Timeline events (title, event_date, topic), FK → documents |

### Initialization

Database tables are automatically created on `softwiki init`. The SQLite file is created by `get_db_url()` which auto-creates the directory and returns a connection string on first access.

---

## LightRAG JSON Storage

LightRAG has its own independent data storage, operating outside the SQLite system. It defaults to a JSON file-based backend requiring no additional infrastructure.

### Directory

```
{WORKSPACE_DIR}/.softwiki/lightrag/
├── graph_chunk_entity_relation.graphml   # NetworkX graph structure (XML)
├── vdb_entities.json                     # Entity vectors (NanoVectorDB)
├── vdb_relationships.json                # Relationship vectors (NanoVectorDB)
├── vdb_chunks.json                       # Chunk vectors (NanoVectorDB)
├── kv_store_full_docs.json               # Full document KV metadata
├── kv_store_text_chunks.json             # Text chunk KV metadata
├── kv_store_llm_response_cache.json      # LLM response cache (KV)
└── kv_store_entity_meta.json             # Entity metadata (KV)
```

### File Descriptions

| File | Storage Backend | Format | Content |
|---|---|---|---|
| `*graphml` | NetworkXStorage | GraphML (XML) | Graph topology of nodes (entities) + edges (relationships) |
| `vdb_*.json` | NanoVectorDBStorage | JSON | Embedding vectors + metadata; each file includes `embedding_dim` |
| `kv_store_*.json` | JsonKVStorage / JsonDocStatusStorage | JSON | Pure key-value metadata, document status, LLM cache |

### Dimension Consistency Check

LightRAG validates on startup that the configured embedding dimension matches the `embedding_dim` stored in existing NanoVectorDB files. On mismatch, startup is rejected with a prompt to delete `.softwiki/lightrag/` and re-ingest.

---

## PostgreSQL

### Use Cases

When the workspace data scale or concurrent access needs exceed SQLite + JSON file capacity, switch LightRAG storage to PostgreSQL.

### Configuration

| Environment Variable | Value |
|---|---|
| `LIGHTRAG_STORAGE` | `postgres` |
| `LIGHTRAG_PG_URL` | `postgresql://user:pass@host:5432/softwiki` |

### Backend Mapping

When `LIGHTRAG_STORAGE=postgres`, LightRAG automatically uses the following PostgreSQL implementations:

| Abstraction Layer | JSON Default Implementation | PostgreSQL Implementation |
|---|---|---|
| KV Storage | `JsonKVStorage` | `PGKVStorage` |
| Vector Storage | `NanoVectorDBStorage` | `PGVectorStorage` |
| Graph Storage | `NetworkXStorage` | `PGGraphStorage` |
| Doc Status | `JsonDocStatusStorage` | `PGDocStatusStorage` |

### System Dependencies

Using the PostgreSQL backend requires:

- **Python**: `asyncpg` (async PostgreSQL driver)
- **PostgreSQL**: `pgvector` extension (vector similarity search)

```bash
# Python dependency
pip install asyncpg

# PostgreSQL extension
CREATE EXTENSION vector;
```

### Notes

- PostgreSQL only affects the **LightRAG layer**. Main data (documents, chunks, claims, etc.) remains in SQLite.
- Existing JSON storage data is **not automatically migrated** when switching backends. Requires re-ingestion.
