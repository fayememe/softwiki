# Extension Points

> softwiki's extensibility design: storage backends, module toggles, optional dependencies, and external abstraction boundaries.
>
> Related docs: [Architecture Overview](../01-architecture/overview.md) | [RAG Engine](rag-engine.md) | [Data Model](data-model.md)

---

## Pluggable Storage Backends

LightRAG defines **4 independent storage types**, each supporting multiple interchangeable backend implementations:

| Storage Type | Purpose | Optional Backends |
|---|---|---|
| **KV** | Key-value storage (LLM cache, metadata, etc.) | `JsonKVStorage` (default), `PGKVStorage`, `RedisKVStorage` |
| **Vector** | Vector index (entity/relation/chunk embeddings) | `NanoVectorDBStorage` (default), `PGVectorStorage`, `QdrantStorage`, `MilvusStorage` |
| **Graph** | Knowledge graph (entity-relationship graph) | `NetworkXStorage` (default), `PGGraphStorage`, `Neo4JStorage` |
| **Doc Status** | Document processing status tracking | `JsonDocStatusStorage` (default), `PGDocStatusStorage` |

### Switching Backends

Storage backend selection is entirely environment-driven, **no code changes required**:

```python
# softwiki/graph_rag/adapter.py — _storage_config() + initialize()
backend = os.getenv("LIGHTRAG_STORAGE", "json")
```

- **`LIGHTRAG_STORAGE=json`** (default) — Uses JSON files + NetworkX + NanoVectorDB, zero external dependencies.
- **`LIGHTRAG_STORAGE=postgres`** — Uses PostgreSQL as unified backend; requires `LIGHTRAG_PG_URL`.

In PostgreSQL mode, all four storage types (KV, Vector, Graph, Doc Status) switch to their PG implementations:

```python
# adapter.py initialize():
if store_cfg["backend"] == "postgres":
    from lightrag.kg.postgres_impl import (
        PGKVStorage, PGVectorStorage,
        PGGraphStorage, PGDocStatusStorage,
    )
    kv_storage = PGKVStorage
    vector_storage = PGVectorStorage
    graph_storage = PGGraphStorage
    doc_status_storage = PGDocStatusStorage
```

Future backends like Redis (KV), Qdrant / Milvus (Vector), Neo4J (Graph) can be added similarly.

### Dimension Safety

When switching embedding models, `_check_dimension_mismatch()` detects whether existing vector index dimensions match the new configuration. On mismatch, initialization is blocked with clear remediation instructions (delete storage directory and re-ingest, or revert configuration). **No auto-rebuild** to prevent silent data corruption.

---

## Module Toggles

softwiki's 5 knowledge processing modules can be independently enabled/disabled via the `ENABLED_MODULES` environment variable:

| Module ID | Function | Default State |
|---|---|---|
| `rag` | Hybrid retrieval (Dense + BM25 + RRF) | Enabled |
| `graph` | Knowledge graph (entity-relation extraction + LightRAG) | Enabled |
| `claimdb` | Claim extraction and query | Enabled |
| `timeline` | Timeline event extraction and query | Enabled |
| `llmwiki` | LLM Wiki page compilation | Enabled |

### Configuration

```bash
export ENABLED_MODULES=rag,graph,claimdb,timeline,llmwiki   # All enabled (default)
export ENABLED_MODULES=rag,claimdb                           # Only rag and claimdb
export ENABLED_MODULES=                                      # All disabled
```

### Implementation

`softwiki/config.py`'s `is_module_enabled()`:

```python
def is_module_enabled(module_name: str) -> bool:
    enabled_str = os.getenv("ENABLED_MODULES", "rag,graph,claimdb,timeline,llmwiki")
    enabled_list = [m.strip().lower() for m in enabled_str.split(",") if m.strip()]
    return module_name.strip().lower() in enabled_list
```

### Scope of Effect

All extraction and query paths respect the module toggle:

- **Extraction pipeline** (`softwiki/extraction/processor.py`): Claim, Graph, and Timeline extractors each check `is_module_enabled()` before running; disabled modules are skipped.
- **Answer engine** (`softwiki/intelligence/answer_engine.py`): 5-layer context fusion (RAG → ClaimDB → Graph → Timeline → LLM Wiki) independently checks `is_module_enabled()` per layer; disabled layers do not participate in retrieval or LLM synthesis.
- **API layer** (`softwiki/api/server.py`): `/api/modules` endpoint returns all modules' enabled states.

### Composition Examples

| Scenario | ENABLED_MODULES | Effect |
|---|---|---|
| Pure RAG knowledge base | `rag` | Only hybrid retrieval and QA, no graph/claim/timeline extraction |
| Graph-enhanced research | `rag,graph,timeline` | RAG + knowledge graph + timeline, no claims or Wiki |
| Lightweight claim tracking | `claimdb` | Only claim extraction and query, no vector index or LightRAG |

---

## Optional Dependencies

softwiki defines optional install groups via Python `[project.optional-dependencies]`:

```toml
# pyproject.toml
[project.optional-dependencies]
graph = [
    "lightrag-hku>=1.5.0",
]
dev = [
    "pytest>=7.0.0",
]
```

| Extra | Install Command | Included Dependencies | Purpose |
|---|---|---|---|
| Base | `pip install softwiki` | fastapi, uvicorn, click, sqlalchemy, openai, numpy, ... | Core features (RAG, search, API) |
| `graph` | `pip install softwiki[graph]` | lightrag-hku | Knowledge graph multi-hop reasoning (LightRAG) |
| `dev` | `pip install softwiki[dev]` | pytest | Development and testing |

```bash
# Typical installation
pip install softwiki[graph]   # Production deployment (with graph capabilities)
pip install softwiki[dev]     # Development environment
pip install softwiki[graph,dev]  # Full-featured dev environment
```

### Design Principles

- `lightrag-hku` as optional dependency: LightRAG is large and not needed for some scenarios (e.g., users only using basic RAG), so it's placed under the `graph` extra for on-demand installation.
- Runtime detection via `has_lightrag_credentials()` (`adapter.py`): when credentials are not ready, LightRAG features silently degrade without import errors.
- `dev` extra contains test toolchain only, no third-party test helpers — kept minimal.

---

## External Abstraction Boundaries

### MCP is the Sole Capability Boundary

MCP (Model Context Protocol) is softwiki's **formal and sole capability boundary**. All external tools interact with softwiki via the MCP protocol (stdio JSON-RPC):

```
External AI Tools       Control Flow          softwiki
────────────────     ──────────          ──────────
opencode               ──── MCP ────▶    MCP Server → Core
Claude Desktop         ──── MCP ────▶    MCP Server → Core
Cursor                 ──── MCP ────▶    MCP Server → Core
Custom Agent           ──── MCP ────▶    MCP Server → Core
WebUI (Next.js)        ──── REST ───▶    API Server → Core
Shell TUI              ──── MCP ────▶    MCP Server → Core
```

### Core Constraints

1. **Core has zero external dependencies** — All functionality of the Core layer (ingestion, extraction, intelligence, source_store, rag, wiki, etc.) **can be used directly via CLI**, without relying on any external AI tool (opencode, Claude, Cursor, etc.).

2. **Shell TUI calls Core via MCP** — The interactive TUI started by `./sw shell` communicates with Core internally via an MCP stdio subprocess, **never importing Core modules directly**. This enforces a unified capability boundary.

3. **WebUI calls via REST API** — The Next.js frontend only consumes FastAPI endpoints exposed by `softwiki/api/server.py`, never accessing internal Python APIs.

4. **MCP Server runs independently** — `python -m softwiki.mcp.server` runs as a standalone stdio process, which can be registered in any MCP host's configuration (Claude Desktop, opencode, Cursor, etc.).

### Extension Methods

| Extension Target | Method | Example |
|---|---|---|
| New MCP tool | Add `@mcp.tool()` function in `softwiki/mcp/server.py` | `@mcp.tool() async def custom_query(...)` |
| New REST endpoint | Add FastAPI router in `softwiki/api/server.py` | `@router.post("/api/custom")` |
| New CLI command | Add Click group in `softwiki/cli/main.py` | `@cli.command() def export(): ...` |
| New storage backend | Implement LightRAG Storage interface + env dispatch branch | See `adapter.py initialize()` backend switch |
| New knowledge module | Add new Extractor in extraction + new context layer in answer_engine | Reuse `is_module_enabled()` guard |

### Disallowed Extensions

- **Core importing external tools directly** — Must not import opencode, claude, etc. SDKs in Core.
- **Bypassing MCP for capability exposure** — All external programmable entry points must go through MCP or REST API; no internal Python functions exposed directly to external agents.

---

## Summary

| Extension Dimension | Mechanism | Configuration Point | Scope |
|---|---|---|---|
| Storage backends | LightRAG Storage interface + env vars | `LIGHTRAG_STORAGE` / `LIGHTRAG_PG_URL` | KV, Vector, Graph, Doc Status |
| Module toggles | `is_module_enabled()` + `ENABLED_MODULES` | Environment variable | Extraction pipeline, answer engine 5 layers |
| Optional deps | `pyproject.toml` extras | pip install | graph, dev dependency groups |
| External boundary | MCP / REST / CLI | — | All external interactions via one of three interfaces |
