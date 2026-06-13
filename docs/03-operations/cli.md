# CLI Command Reference

> **Scope**: Complete reference for all softwiki CLI commands, options, and examples.
> **Audience**: Operators and power users working in the terminal.

---

## Global Options

The following options apply to all commands and must be specified before the command:

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--workspace` | `-w` | `str` | `WORKSPACE_DIR` env or `workspace/default` | Specify workspace path (absolute path or name) |
| `--mode` | | `choice` | `wiki-admin` | Execution mode: `wiki-admin`, `wiki-manage`, `wiki-study`, `wiki-work` |
| `--session-id` | | `str` | `None` | Session ID for output routing (user modes only) |

**Mode description**:

| Mode | Permissions | Purpose |
|---|---|---|
| `wiki-admin` | Read/write | Full admin access, all operations |
| `wiki-manage` | Read/write | Manage workspace content, no system-level operations |
| `wiki-study` | Read-only | Query and analysis only, writes disabled |
| `wiki-work` | Read-only | Work mode, query and analysis only |

> **Note**: `init`, `ingest`, `index` are disabled in `wiki-study` and `wiki-work` modes. `wiki build` is disabled in `wiki-study` mode.

On startup, the CLI displays the active workspace and mode:

```
[*] Active Workspace: /home/user/softwiki/workspace/my-project
[*] User Mode Active (WIKI-WORK). Session Output: output/ses_abc123/
```

---

## Command Reference

### `init` — Initialize Workspace

Initialize folder structure, configuration files, and database tables.

**Usage**:

```bash
softwiki [global options] init
```

**Description**: Creates the following directory structure:

```
workspace/<name>/
├── raw/html/
├── raw/pdf/
├── raw/markdown/
├── raw/api/
├── processed/documents/
├── processed/chunks/
├── processed/embeddings/
├── processed/extracted/
├── export/wiki/countries/
├── export/wiki/organizations/
├── export/wiki/topics/
├── export/wiki/events/
├── export/wiki/claims/
├── export/wiki/reports/
├── configs/sources.yaml
├── configs/model_profiles.yaml
└── scope.md
```

Copies default config files from templates (`sources.yaml`, `model_profiles.yaml`, `scope.md`), creates placeholders if templates are missing. Initializes database tables and pre-populates source configs from `sources.yaml`.

**Examples**:

```bash
# Initialize default workspace
softwiki init

# Initialize specific workspace
softwiki -w ~/research/my-project init
```

---

### `ingest` — Import Documents

Import a document, clean it, extract metadata, run extraction pipeline (entities, relationships, events, claims), and save to database.

**Usage**:

```bash
softwiki [global options] ingest --url <URL> [--source-id <ID>]
softwiki [global options] ingest --file <PATH> [--source-id <ID>]
```

**Options**:

| Option | Type | Required | Description |
|---|---|---|---|
| `--url` | `str` | See note | Import content from a web URL |
| `--file` | `str` | See note | Import content from a local PDF file |
| `--source-id` | `str` | No | Associate with a predefined source ID from `configs/sources.yaml` |

> `--url` and `--file` must specify at least one, cannot be used together.

**Flow**:

1. Fetch content (web scraping or PDF extraction)
2. Validate document is in scope via scope check (`scope.md`)
3. Deduplicate based on content hash and URL
4. Save to document database
5. Run extraction pipeline: entities, relationships, events, claims

**Examples**:

```bash
# Import from URL, no source association
softwiki ingest --url https://example.com/article

# Import from URL with source association
softwiki ingest --url https://example.com/report --source-id world-bank

# Import from local PDF
softwiki ingest --file /path/to/document.pdf

# Import PDF with source association
softwiki ingest --file ./paper.pdf --source-id academic-journal
```

**Output**:

```text
Ingesting URL: https://example.com/article...
Created Document ID 42: 'Article Title'
Running extraction pipeline...
Extraction complete: 15 claims, 8 entities, 12 relationships, 3 events extracted.
```

---

### `index` — Rebuild Search Index

Rebuild dense vector index (embeddings) and sparse BM25 keyword index for all documents.

**Usage**:

```bash
softwiki [global options] index
```

**Description**: For each document in the workspace database:

1. Delete existing chunks
2. Chunk the cleaned text
3. Generate embedding vectors for all chunks
4. Update FAISS vector index
5. Rebuild BM25 keyword index

**Examples**:

```bash
# Rebuild all indexes
softwiki index

# Rebuild index in another workspace
softwiki -w my-project index
```

**Output**:

```text
Building search indexes...
Indexing 156 chunks...
Generating embeddings...
Vector index successfully updated.
BM25 keyword index successfully updated.
Indexing complete!
```

---

### `ask` — Research Question

Answer research questions using a hybrid RAG retrieval + graph context + LLM synthesis system.

**Usage**:

```bash
softwiki [global options] ask "<question>"
```

**Parameters**:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `question` | `str` | Yes | Natural language research question |

**Examples**:

```bash
# Basic research question
softwiki ask "What are the key drivers of de-dollarization?"

# Multi-language query
softwiki ask "What are the trends in central bank gold reserves?"

# Question in a specific workspace
softwiki -w geo-economics ask "How has BRICS expansion affected USD reserve share?"
```

**Output**: A comprehensive answer with citations, sourced from retrieved chunks and graph context.

---

### `wiki` — Wiki Page Management

#### `wiki build` — Build Wiki Page

Compile and generate a Markdown wiki page for a topic ID.

**Usage**:

```bash
softwiki [global options] wiki build --topic <TOPIC_ID>
```

**Options**:

| Option | Type | Required | Description |
|---|---|---|---|
| `--topic` | `str` | Yes | Topic ID to build page for |

> Disabled in `wiki-study` mode.

**Examples**:

```bash
# Build wiki page for a country topic
softwiki wiki build --topic de-dollarization

# Build wiki page for an organization topic
softwiki wiki build --topic world-bank
```

**Output**:

```text
Generating wiki page for topic: 'de-dollarization'...
Wiki page successfully written to: /path/to/workspace/export/wiki/topics/de-dollarization.md
```

---

### `shell` — Launch Interactive TUI

Launch an interactive research and management terminal user interface (TUI).

**Usage**:

```bash
softwiki [global options] shell [options]
```

**Options**:

| Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `--workspace` | `-w` | `str` | `WORKSPACE_DIR` or `workspace/default` | Workspace name or path |
| `--model` | `-m` | `str` | `ANALYSIS_MODEL` or `gemini-2.5-flash` | Model for analysis |
| `--session` | `-s` | `str` | `None` | Custom session name suffix. Terminal session ID = `{workspace}-{mode}-{session}` |

> **Note**: `--model` and `--session` are global flags for the TUI help commands. Commands issued through the TUI should use the `open-code` workflow, which calls tools using the context injected at shell startup.

**Examples**:

```bash
# Launch TUI with default workspace
softwiki shell

# Launch TUI with specific workspace and model
softwiki -w geo-economics shell -m gemini-2.5-pro

# Launch TUI with custom session name
softwiki shell --workspace my-project --session round-2
```

---

### `api` — Start REST API Server

Start the REST API server.

**Usage**:

```bash
softwiki [global options] api [options]
```

**Options**:

| Option | Type | Default | Description |
|---|---|---|---|
| `--port` | `int` | `8000` | API server port |
| `--host` | `str` | `127.0.0.1` | API server bind host |

**Examples**:

```bash
# Start API server on default address
softwiki api

# Start API server on custom port
softwiki api --port 9000

# Bind to all interfaces
softwiki api --host 0.0.0.0 --port 8080
```

---

### `graph` — Graph Management

#### `graph list` — List Entities and Relationships

List all extracted entities and relationships in the workspace.

**Usage**:

```bash
softwiki [global options] graph list
```

**Output**:

```text
=== Entities (24) ===
- United States [country]: Federal republic in North America
- Federal Reserve [organization]: Central bank of the United States
- USD [currency]: United States Dollar
- BRICS [organization]: Intergovernmental organization

=== Relationships (47) ===
- United States --(imposes_sanctions_on)--> Russia (Conf: 0.92)
  Note: Sanctions imposed after 2022 invasion
- China --(holds_reserves_in)--> USD (Conf: 0.85)
```

---

### `timeline` — Timeline Management

#### `timeline list` — List Timeline Events

List all extracted events in chronological order.

**Usage**:

```bash
softwiki [global options] timeline list
```

**Output**:

```text
=== Chronological Events (12) ===
- [2022-02-24] Russia-Ukraine Conflict Begins (Topic: geopolitics)
  Description: Full-scale invasion of Ukraine by Russia
- [2023-08-22] BRICS Summit 2023 (Topic: international-relations)
  Description: BRICS announces expansion to include new members
- [2024-10-22] BRICS Summit 2024 (Topic: international-relations)
  Description: Further discussion on de-dollarization and trade settlement
```

---

## Exit Codes

| Exit Code | Meaning |
|---|---|
| `0` | Success |
| `1` | General error (invalid parameters, operation failure, document out of scope, etc.) |

---

## Usage Patterns

### Managing Workspaces

```bash
# Initialize and setup
softwiki -w my-research init

# Import documents
softwiki -w my-research ingest --url https://example.com/article --source-id source-1
softwiki -w my-research ingest --file ./papers/report.pdf

# Rebuild index
softwiki -w my-research index
```

### Research Queries

```bash
# Query in read-only mode
softwiki -w my-research --mode wiki-work ask "What are the latest developments?"

# Launch TUI for interactive research
softwiki -w my-research --mode wiki-work shell
```

### Wiki Publishing

```bash
# Generate and view topic page
softwiki wiki build --topic my-topic
```
