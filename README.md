# softwiki

**Multi-Strategy Research Intelligence Engine.** Unifies RAG, GraphRAG, and LLM-Wiki (Karpathy architecture) into a single MCP-powered knowledge platform. Designed for deep research workflows across isolated knowledge bases.

```mermaid
graph TD
    RS["Raw Sources<br/>Web / PDFs / APIs / Notes"] --> ING["Ingestion Pipeline<br/>fetch → clean → dedup"]

    ING --> SS["Source Store<br/>SQLite: documents table<br/>canonical evidence"]
    SS --> RAG["RAG Index<br/>BM25 + Vector (hybrid)<br/>evidence retrieval"]
    SS --> EX["Extraction Pipeline<br/>LLM + rule-based"]

    EX --> CDB["ClaimDB<br/>actor / stance / topic<br/>structured reasoning"]
    EX --> KG["Knowledge Graph<br/>entities + relations<br/>relationship reasoning"]
    EX --> TL["Timeline<br/>chronological events<br/>temporal reasoning"]

    RAG --> INTEL["Intelligence Layer<br/>AnswerEngine"]
    CDB --> INTEL
    KG --> INTEL
    TL --> INTEL

    INTEL --> WIKI["LLM Wiki<br/>compounding markdown pages<br/>human-readable synthesis"]

    style SS fill:#4a90d9,color:#fff
    style RAG fill:#7b68ee,color:#fff
    style CDB fill:#2ecc71,color:#fff
    style KG fill:#f39c12,color:#fff
    style TL fill:#e74c3c,color:#fff
    style WIKI fill:#9b59b6,color:#fff
```

## Why softwiki?

> **Not another RAG tool.** softwiki is a knowledge operating system — orchestrating heterogeneous retrieval strategies, autonomous extraction pipelines, and agentic collaboration through the Model Context Protocol.

### Hybrid Cognitive Architecture

| Strategy | Method | Use Case |
|---|---|---|
| **RAG** | Dense + BM25 hybrid, RRF fusion | Factual retrieval, citation-backed answers |
| **GraphRAG** | LightRAG — BFS subgraph traversal, 6 query modes | Multi-hop reasoning, relational deep-dives |
| **LLM-Wiki** | Karpathy-style compounding markdown | Persistent knowledge synthesis, human-readable reports |

### Intelligence Spectrum

- **Per-Scope Intelligence** — Each knowledge base operates within a defined scope (scope.md), auto-rejecting out-of-domain queries
- **Multi-Layer Extraction** — Claims (actor/stance), entities/relations, timeline events — extracted asynchronously per document
- **Confidence Calibration** — Every answer carries a confidence assessment grounded in source provenance

### Elastic Architecture

```
Laptop                        → Cluster
─────────────────────────────────────────
SQLite + JSON files           → PostgreSQL + Qdrant + Neo4J
Single-user Shell             → Multi-tenant MCP Gateway
One workspace                 → N isolated knowledge bases
```

One env var changes the storage backend. Zero code changes.

### Multi-Agent Ecosystem

softwiki speaks every agent protocol — not locked to one ecosystem:

| Interface | Protocol | Compatible With |
|---|---|---|
| **MCP (stdio)** | stdin/stdout JSON-RPC | Claude, opencode, Cursor, Zed, Windsurf |
| **MCP (SSE)** | HTTP SSE transport | Any remote agent (Hermes, custom runners) |
| **OpenAI API** | `/v1/chat/completions` | LobeChat, Open WebUI, LibreChat, NextChat |
| **REST API** | FastAPI, JSON | Custom integrations, curl, scripts |

17 MCP tools exposed across retrieval, graph, ingestion, synthesis, and discovery domains — any MCP-compatible agent becomes a native knowledge worker.

### Multi-Surface Experience

- **Shell TUI** — opencode-powered research shell, zero core dependency
- **WebUI** — Next.js 16 dashboard, dark theme, session management, Wikipedia-style reader
- **Headless** — MCP stdio server for any MCP-compatible host

## Quick Start

```bash
pip install softwiki[graph]
softwiki init
softwiki ingest --url "https://example.com/article"
softwiki ask "Synthesize the key arguments"
softwiki shell
```

## Documentation

[Architecture, Design Whitepaper, Operations & Guides →](docs/README.md)

## Requirements

- Python 3.10+
- opencode (optional, for Shell TUI)

## License

MIT
