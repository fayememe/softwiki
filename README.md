# SoftWiki

**Domain-independent research intelligence and knowledge management engine.** Exposes RAG, knowledge graphs, timeline analysis, and auto-generated wikis through the Model Context Protocol (MCP).

![SoftWiki WebUI](docs/screenshot.svg)

## Features

- **MCP-First** — 17 MCP tools for query, ingest, search, graph traversal, wiki compilation
- **LightRAG GraphRAG** — Multi-hop reasoning, BFS subgraph exploration, 6 query modes
- **Multi-Layer Extraction** — Claims, entities/relations, timeline events, LLM-Wiki pages
- **Hybrid Search** — Dense vector + BM25 with RRF fusion, citation management
- **WebUI** — Next.js 16 dashboard with session management and Wikipedia-style reader
- **Separated LLM/Embedding** — Different providers per task (e.g., DeepSeek LLM + Gemini embedding)
- **Pluggable Storage** — JSON (zero-config) or PostgreSQL, switched by env var

## Quick Start

```bash
pip install softwiki[graph]
softwiki init
softwiki ingest --url "https://example.com/article"
softwiki ask "What are the key findings?"
softwiki shell
```

## Documentation

Full documentation at [docs/README.md](docs/README.md) — architecture, design whitepaper, operations, and guides.

## Requirements

- Python 3.10+
- opencode (for Shell TUI, optional)

## Contributing

Contributions welcome. See the [docs](docs/README.md) for architecture overview. Run tests with:

```bash
pip install -e ".[dev]"
PYTHONPATH=. pytest
```

## License

MIT
