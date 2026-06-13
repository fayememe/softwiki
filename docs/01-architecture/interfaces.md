# Interfaces

> **Scope**: All external-facing interfaces of softwiki — MCP tools, REST API endpoints, and CLI commands.
> **Audience**: Developers integrating with softwiki or building automation on top of it.

---

## MCP Tools

softwiki exposes 17 tools via the Model Context Protocol (MCP). Each tool is a `@mcp.tool()` function in `softwiki/mcp/server.py`.

Permission levels:
- **read** — Query only; no state change.
- **write** — Modifies workspace state (database, indexes, files).
- **admin** — System-level operations with elevated restrictions.

| Tool Name | Function | Permissions |
|---|---|---|
| `status` | Get workspace status including database statistics (document/chunk/claim counts). | read |
| `search` | CJK-aware hybrid search (vector + BM25) returning formatted results. | read |
| `retrieve` | Hybrid search returning structured chunk metadata (IDs, scores) for programmatic use. | read |
| `ask` | Research question via hybrid RAG retrieval + graph context + LLM synthesis (structured answer with citations). | read |
| `wiki_read` | Read a previously compiled wiki page by topic ID (returns markdown). | read |
| `source_list` | List all ingested documents with basic metadata (source, date, status). | read |
| `source_preview` | Preview the full cleaned text of a source document by its ID. | read |
| `graph_query` | Query the knowledge graph for entities and relationships (with partial-match filters). | read |
| `lightrag_query` | Query the LightRAG knowledge graph with graph traversal (modes: local/global/hybrid/mix/naive). | read |
| `lightrag_explore` | BFS traversal around an entity in the LightRAG graph. | read |
| `lightrag_status` | Get LightRAG engine status (initialization, graph nodes/edges). | read |
| `timeline_query` | Query timeline events in chronological order (with topic/date-range filters). | read |
| `claim_query` | Query source-backed assertions (with actor/topic/stance filters). | read |
| `web_search` | Server-side web search proxy (Tavily / SerpAPI / Bing). Disabled by default. | read |
| `ingest` | Ingest a new document from a URL or local PDF into the workspace (includes chunking, embedding, and background extraction). | write |
| `index` | Rebuild vector (dense) and BM25 (keyword) search indexes for all documents. | write |
| `wiki_build` | Compile and generate a markdown wiki page for a topic ID. | write |

> **Note**: `ingest`, `index`, and `wiki_build` are disabled in read-only modes (`study`, `work`, `wiki-study`, `wiki-work`). `wiki_build` is additionally disabled in `study` / `wiki-study` modes only.

---

## REST API

softwiki provides a REST API via `softwiki/api/server.py`, built with **FastAPI**. The server runs on `http://127.0.0.1:8000` by default (configurable via CLI `--port` / `--host`).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/status` | Workspace status (document/chunk/claim/entity/relationship/event counts + module flags). |
| `GET` | `/api/modules` | Status of all modular subsystems (rag, graph, claimdb, timeline, llmwiki). |
| `GET` | `/api/documents` | List all ingested documents with metadata, ordered by newest first. |
| `DELETE` | `/api/documents/{doc_id}` | Delete a document (cascade deletes chunks, claims, events, relationships). |
| `GET` | `/api/claims` | List all extracted claims with actor, stance, confidence. |
| `GET` | `/api/timeline` | List all timeline events sorted chronologically. |
| `GET` | `/api/graph` | List all entities and relationships forming the knowledge graph. |
| `POST` | `/api/ask` | Research question via hybrid RAG + LLM synthesis (returns answer + citation sources). |
| `POST` | `/api/ingest/url` | Ingest a web URL into the workspace. |
| `POST` | `/api/ingest/file` | Upload and ingest a PDF file. |
| `POST` | `/api/index` | Chunk all documents and rebuild dense embeddings + BM25 index. |
| `GET` | `/api/wiki/topics` | List available wiki topics (from `topics.yaml` or distinct claim topics). |
| `POST` | `/api/wiki/build` | Generate and write a topic wiki page to workspace exports. |
| `GET` | `/api/wiki/page/{topic}` | Read an already-generated wiki page without rebuilding. |

> **Note**: Write endpoints (`POST /api/ingest/*`, `POST /api/index`, `DELETE /api/documents/*`) return HTTP 403 when `SOFTWIKI_MODE` is `study`, `work`, `wiki-study`, or `wiki-work`. `POST /api/wiki/build` returns 403 in `study` / `wiki-study` modes.

---

## CLI

The CLI is built with **Click** and defined in `softwiki/cli/main.py`. All commands live under the top-level `softwiki` group.

### Global Options

| Option | Default | Description |
|---|---|---|
| `--workspace, -w` | `WORKSPACE_DIR` env or `workspace/default` | Workspace directory path. |
| `--mode` | `wiki-admin` | Execution mode: `wiki-admin`, `wiki-manage`, `wiki-study`, `wiki-work`. |
| `--session-id` | — | Session ID for output routing (user modes only). |

### Commands Grouped by Purpose

#### Workspace

| Command | Description |
|---|---|
| `init` | Initialize workspace: create folder structure, copy default configs (`sources.yaml`, `model_profiles.yaml`, `scope.md`), seed source definitions, create database tables. |

#### Ingestion

| Command | Options | Description |
|---|---|---|
| `ingest` | `--url <URL>` | Ingest content from a web URL. |
| | `--file <PATH>` | Ingest content from a local PDF file. |
| | `--source-id <ID>` | Associate with a predefined source in `configs/sources.yaml`. |

#### Index

| Command | Description |
|---|---|
| `index` | Chunk all documents, generate dense embeddings, and rebuild the BM25 keyword index. |

#### Query

| Command | Arguments | Description |
|---|---|---|
| `ask` | `<question>` | Research question via hybrid RAG + graph context + LLM synthesis. |

#### Wiki

| Command | Options | Description |
|---|---|---|
| `wiki build` | `--topic <ID>` | Compile and generate a markdown wiki page for a topic ID. |

#### Graph

| Command | Description |
|---|---|
| `graph list` | List all extracted entities and relationships in the workspace. |

#### Timeline

| Command | Description |
|---|---|
| `timeline list` | List all chronological events in the workspace. |

#### Shell

| Command | Options | Description |
|---|---|---|
| `shell` | `--workspace, -w <PATH>` | Workspace to open (name or absolute path). |
| | `--model, -m <NAME>` | Model override for analysis (e.g. `gemini-2.5-flash`). |
| | `--session, -s <SUFFIX>` | Custom session name suffix. |
| | | Launches the interactive research and management TUI. |

#### Server

| Command | Options | Description |
|---|---|---|
| `api` | `--port <PORT>` (default: `8000`) | Port to bind the REST API server. |
| | `--host <HOST>` (default: `127.0.0.1`) | Host to bind the REST API server. |
| | | Starts the FastAPI server via `uvicorn`. |

---

## Summary

The three interfaces provide increasing levels of automation:

- **CLI** — Interactive and scriptable use for workspace management, ingestion, and querying.
- **REST API** — HTTP integration for web frontends (Next.js) and external services.
- **MCP Tools** — AI-agent-native access via the Model Context Protocol, enabling autonomous research workflows.

All three share the same underlying domain logic (chunking, embedding, hybrid search, extraction, wiki generation) but differ in access patterns and suitability for automation.
