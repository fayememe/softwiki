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

---

## 向量后端：文件 vs pgvector（2026-11-25）

### 切换开关

```
SOFTWIKI_VECTOR_BACKEND=file   # 默认，.npz + 内存暴力余弦
SOFTWIKI_VECTOR_BACKEND=pg     # PostgreSQL + pgvector
```

`LocalVectorStore` 现在是门面：调用点不变，后端由环境变量决定。文件后端保留，
切回去只需改环境变量并重启 api/mcp。

### pgvector 表

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE chunk_embeddings (
  chunk_id  bigint PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  model     text NOT NULL DEFAULT '',
  dim       integer NOT NULL DEFAULT 0,
  embedding vector(1536) NOT NULL
);
CREATE INDEX ix_chunk_embeddings_hnsw ON chunk_embeddings
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
```

- 写：`INSERT ... ON CONFLICT (chunk_id) DO UPDATE`，增量、幂等；
- 查：`ORDER BY embedding <=> $q LIMIT k`；
- 删 chunk 级联删向量，不再有“索引指向已删 chunk”。

### 查询期的两个必需设置

| 设置 | 原因 |
|---|---|
| `SET LOCAL hnsw.ef_search = max(40, k*4)` | ef_search < k 时 top-k 召回显著下降 |
| `SET LOCAL enable_seqscan = off` | 40k×1536 时 planner 会选 seq scan（~400ms），强制走 HNSW（~4ms） |

### 迁移脚本

```bash
python scripts/migrate_vectors_to_pg.py --batch 200 --index hnsw --samples 20 --json /tmp/report.json
```

流程：读 npz → 用 `chunks` 过滤孤儿向量 → 分批 upsert → 建 HNSW → 数量校验 +
file/pg top-50 召回对比。脚本幂等，可重复执行。

### 实测（2026-11-25）

| 库 | live 向量 | 孤儿丢弃 | recall@50 | pg 查询 p50 |
|---|---|---|---|---|
| javis armkb | 39,870 | 39,870 | 99.7%（min 94%） | 4.7 ms |
| trial coffee | 3,489 | 0 | 100% | 4.2 ms |
| trial ai-history | 5,497 | 0 | 100% | 4.4 ms |

对比文件后端（armkb）：`FileVectorStore` 加载 npz **614 ms**、单次 top-10 检索 **~348 ms**；
pgvector 单次 **4.7 ms**，进程不再常驻 936 MB float64 矩阵。
存储代价：armkb `chunk_embeddings` 表 ~825 MB（含 TOAST）+ HNSW 索引 312 MB。

### 踩坑

- armkb 的 npz 有**一半是孤儿**（79,740 条里 39,870 条 chunk 已不存在）——迁移必须过滤；
- 表必须带维度（`vector(1536)`），无维度的 `vector` 不利于索引；
- 索引在**灌完数据之后**建，否则构建很慢；
- trial-host 连不上 Docker Hub：用可达的镜像源（如 `docker.1ms.run`）拉取后
  `docker tag` 成 `pgvector/pgvector:pg16`；
- compose 用 `POSTGRES_IMAGE` 变量切换镜像（javis CI `.env`、trial `.env/.env.ai`），
  同 major 版本的 PGDATA 可直接复用。
