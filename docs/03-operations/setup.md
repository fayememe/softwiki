# Setup & Installation

> **Scope**: System requirements, Python environment, workspace initialization, configuration templates, multi-workspace management, MCP Server registration.
>
> **Prerequisite reading**: [Architecture Overview](../01-architecture/overview.md) | [Interfaces](../01-architecture/interfaces.md)

---

## System Requirements

| Dependency | Minimum Version | Notes |
|---|---|---|
| Python | 3.10+ | Runs Core, CLI, MCP Server |
| Node.js | 18+ | WebUI only |
| opencode | — | Shell TUI only |

**Known compatible LLM Providers**:

- OpenAI (GPT-4o / GPT-4o-mini / text-embedding-3-small)
- DeepSeek (via OpenAI-compatible API)
- Gemini (via OpenAI-compatible API)
- Groq (via OpenAI-compatible API)

Embedding Provider supports `openai` (API) or `local` (sentence-transformers based).

---

## Installation

### 1. Clone the Project

```bash
git clone <repo-url> softwiki
cd softwiki
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Package

```bash
# Base installation (RAG + Core + MCP + API)
pip install -e .

# Full installation (with dev tools and LightRAG GraphRAG)
pip install -e ".[dev,graph]"
```

Optional dependency groups:

| Group | Includes | Purpose |
|---|---|---|
| `[dev]` | pytest | Run test suite |
| `[graph]` | lightrag-hku | Knowledge graph multi-hop reasoning queries |

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env`, at minimum fill in:

```bash
OPENAI_API_KEY=sk-...           # LLM API Key
OPENAI_API_BASE=https://...     # API endpoint (optional, default OpenAI)
EXTRACTION_MODEL=gpt-4o-mini    # Extraction model
ANALYSIS_MODEL=gpt-4o           # Analysis & synthesis model
EMBEDDING_PROVIDER=openai       # Embedding provider
EMBEDDING_MODEL=text-embedding-3-small
```

Environment variables are auto-loaded from `.env` (`softwiki/config.py:load_env()`), and can also be overridden via shell export.

### 5. Verify Installation

```bash
./sw --help
```

Should display the softwiki CLI command list.

---

## Initialize Workspace

A workspace is softwiki's **independent knowledge base unit**, containing documents, indexes, configuration, and a database, organized as a filesystem directory.

### Default Workspace

```bash
./sw init
```

Creates the following structure in `workspace/default/`:

```
workspace/default/
├── config/               # Workspace configuration
│   ├── scope.md          # Knowledge base scope definition
│   ├── topics.yaml       # Research topic definitions
│   ├── sources.yaml      # Data source trust levels
│   ├── model_profiles.yaml
│   ├── workflows.yaml
│   └── agents.md         # Agent prompt overrides (optional)
├── raw/                  # Raw files
│   ├── html/
│   ├── pdf/
│   ├── markdown/
│   └── api/
├── .softwiki/            # Database & indexes
│   ├── processed.db      # SQLite database
│   ├── index/            # Vector & BM25 indexes
│   └── lightrag/         # LightRAG graph data
├── exports/              # Export artifacts
│   └── wiki/             # Wiki pages
│       ├── topics/
│       ├── organizations/
│       ├── countries/
│       ├── events/
│       ├── claims/
│       └── reports/
└── processed/            # Processing intermediates (embedding vectors, etc.)
    ├── documents/
    ├── chunks/
    ├── embeddings/
    └── extracted/
```

The `init` command automatically:

1. Creates the above folder structure
2. Copies default configuration files from `softwiki/templates/` to `config/`
3. Creates the SQLite database (`.softwiki/processed.db`)
4. Pre-populates data source records from `config/sources.yaml`

### Custom Path

```bash
./sw -w workspace/my-kb init
```

Supports any path:

```bash
./sw -w /data/research/knowledge-base init
```

---

## Multi-Workspace

Each workspace is fully isolated, with its own database, indexes, configuration, and data files.

### Switching Methods

**Method 1: `-w` parameter**

```bash
# Use different workspaces
./sw -w workspace/kb-alpha ingest --url "https://..."
./sw -w workspace/kb-beta ask "What are the key findings?"
```

**Method 2: Environment variable**

```bash
export WORKSPACE_DIR=/data/research/kb-alpha
./sw init
./sw ingest --url "https://..."
```

**Method 3: Path format**

`-w` accepts relative paths (relative to project root) or absolute paths:

```bash
./sw -w workspace/my-kb shell       # relative path
./sw -w /home/user/my-kb shell      # absolute path
```

### Use Cases

| Scenario | Practice |
|---|---|
| Independent research topics | Each topic gets its own workspace |
| Team sharing | Each researcher has their own workspace, shared via `workspace/` directory |
| Phased research | Phase 1 and Phase 2 can be separate workspaces |
| Production/test isolation | Production and test databases use different workspaces |

---

## Configuration Templates

After workspace initialization, the `config/` directory contains the following configuration files:

### scope.md — Knowledge Base Scope

Defines the knowledge base topic boundaries, used by `scope_guard` to automatically filter documents during ingestion.

```markdown
# Knowledge Base Scope

## In Scope
- De-dollarization, central bank reserves, gold, international trade currencies.

## Out of Scope
- Unrelated financial news, stock market updates, recipes, entertainment, sports.
```

### topics.yaml — Research Topic Definitions

```yaml
topics:
  topic-alpha:
    aliases:
      - topic a
      - alpha project
      - first topic
    related:
      - topic-beta
      - topic-gamma

  topic-beta:
    aliases:
      - topic b
      - beta system
      - second topic
    related:
      - topic-alpha
```

Each topic has aliases (for matching) and a related topics list (for Wiki page cross-references).

### sources.yaml — Data Source Trust Levels

```yaml
sources:
  - id: sample_source_1
    name: Sample News Outlet
    type: news                       # official / news / think_tank / academic
    url: https://www.example-news.com/
    trust_level: high                # high / medium / low
    source_country: us
    language: en
```

The `init` command pre-populates all sources from `sources.yaml` into the database; subsequent ingests can associate via `--source-id`.

### model_profiles.yaml — LLM Parameter Overrides

```yaml
profiles:
  cheap_extraction:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.0

  high_quality_analysis:
    provider: openai
    model: gpt-4o
    temperature: 0.2

  local_embedding:
    provider: local
    model: bge-m3
```

Default model selection can be overridden via the `EXTRACTION_MODEL`, `ANALYSIS_MODEL` environment variables, etc.

### workflows.yaml — Workflow Overrides

Defines self-routing workflows used in the Agent shell. Provides five default workflows: `research`, `wiki-compile`, `contribute`, `submit`, `simple-q&a`. Workspace-level configuration does a **deep merge** with the default template.

### agents.md — Agent Prompt Overrides

An optional agent behavior override file. When placed at `config/agents.md`, the Shell TUI auto-loads and appends its content to the default Agent Soul, allowing customization of agent behavior patterns, tool boundaries, and response formats.

---

## Register MCP Server

softwiki exposes knowledge base capabilities to external AI tools via the Model Context Protocol (MCP). The MCP Server runs as an independent process, communicating via stdio JSON-RPC.

### Generic Configuration

Add the following JSON to your AI tool's MCP configuration:

```json
{
  "mcpServers": {
    "softwiki": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "softwiki.mcp.server"],
      "cwd": "/path/to/softwiki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwiki"
      }
    }
  }
}
```

### Platform Configuration Locations

**Claude Desktop**: Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows).

**Cursor**: Configure MCP Servers in Cursor settings.

**opencode**: Edit `opencode.json` or `.opencode/mcp.json`.

**Custom MCP clients**: Any MCP protocol-compatible client can connect via stdio.

### Read-Only Mode

To restrict external tools to query-only, set the environment variable:

```json
"env": {
  "SOFTWIKI_MODE": "wiki-study",
  "WORKSPACE_DIR": "...",
  "PYTHONPATH": "..."
}
```

For the four operating modes, see [Architecture Overview — Operating Modes](../01-architecture/overview.md#operating-modes).

---

## Verify Installation

### CLI Workflow

```bash
# 1. Initialize default workspace
./sw init

# 2. Ingest a document
./sw ingest --url "https://example.com/article"

# 3. Rebuild index
./sw index

# 4. Ask a question
./sw ask "What are the key points of the article?"

# 5. Compile Wiki page
./sw wiki build --topic topic-alpha
```

### MCP Server Heartbeat

The MCP Server produces no log output on startup (stdio protocol). Verify the connection by calling the `softwiki_status` tool from an external MCP client.

---

## FAQ

| Problem | Cause | Solution |
|---|---|---|
| `./sw: No such file or directory` | Virtual environment not created | `python3 -m venv venv && source venv/bin/activate && pip install -e .` |
| `ModuleNotFoundError: softwiki` | PYTHONPATH not set | The `sw` script sets it automatically; for manual runs use `export PYTHONPATH=.` |
| Document rejected (out of scope) | `config/scope.md` scope too narrow | Edit `scope.md` to broaden the scope |
| MCP connection failure | `WORKSPACE_DIR` path incorrect | Ensure both `PYTHONPATH` and `WORKSPACE_DIR` use absolute paths |
