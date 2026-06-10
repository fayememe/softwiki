# softwiki: Research Intelligence & Knowledge Engine

## 1. Project Goal

Build a source-grounded research intelligence and automated knowledge management engine. The system is designed to be domain-independent, allowing it to adapt to financial, medical, corporate, or academic research domains by swapping workspace directories.

The core principles of the architecture:
```text
Workspace Substrate (DB / Indexes / Source Docs) = knowledge substrate
Wiki / Reports (Auto-generated Markdown) = human-readable output layer
```

---

## 2. High-Level Architecture & Workspace Mapping

All assets (database, configs, search indexes, raw crawls, exports) are isolated under a configurable workspace directory:

```text
Host Directory (e.g. workspace/my-workspace/)   --> Mounted into Container (/workspace/)
  ├── configs/
  │     ├── sources.yaml          --> Predefined sources for this domain
  │     ├── topics.yaml           --> Controlled vocabulary / synonyms
  │     └── model_profiles.yaml   --> LLM models and parameters
  ├── softwiki.db                 --> SQLite database for this workspace
  ├── index/
  │     ├── vector_index.npz      --> Dense embeddings vector store
  │     └── bm25_index.pkl        --> BM25 lexical keyword index
  ├── raw/                        --> Ingested raw HTML/PDF documents
  ├── processed/                  --> Processed chunks and metadata
  └── exports/
        └── wiki/                 --> Exported research wiki pages
```

---

## 3. Recommended Repository Structure

```text
softwiki-engine/
├── README.md
├── pyproject.toml
├── setup.py
├── .env.example
├── Makefile
├── sw                           --> CLI wrapper script
│
├── softwiki/                    --> Main engine package
│   ├── __init__.py
│   ├── config.py                --> Workspace path resolution
│   │
│   ├── ingestion/
│   │   ├── normalize.py         --> Whitespace/quotes cleaning
│   │   ├── dedup.py             --> SHA-256 duplicate checking
│   │   ├── pdf_loader.py        --> local PDF text extractor
│   │   └── web_loader.py        --> URL crawler and HTML cleaner
│   │
│   ├── source_store/
│   │   ├── db.py                --> Dynamic SQLAlchemy connection
│   │   ├── models.py            --> SQLite relational models
│   │   └── document_repo.py     --> CRUD operations
│   │
│   ├── rag/
│   │   ├── chunker.py           --> Document-aware chunk splitter
│   │   ├── embedder.py          --> OpenAI & local embedding adapter
│   │   ├── vector_store.py      --> Local NumPy vector index
│   │   ├── bm25_store.py        --> rank_bm25 keyword index
│   │   ├── hybrid_search.py     --> Vector + BM25 search with RRF
│   │   └── citations.py         --> Inline citation manager
│   │
│   ├── extraction/
│   │   └── claim_extractor.py   --> Actor/Topic/Stance LLM extractor
│   │
│   ├── intelligence/
│   │   └── answer_engine.py     --> Citation-backed RAG Q&A generator
│   │
│   ├── wiki/
│   │   └── page_generator.py    --> Markdown topic wiki builder
│   │
│   └── cli/
│       └── main.py              --> CLI click commands
│
└── tests/
    ├── test_ingestion.py
    ├── test_rag.py
    ├── test_extraction.py
    ├── test_answer_engine.py
    └── test_workspace.py        --> Workspace boundary checks
```

---

## 4. Main Modules

### 4.1 Workspace Path Resolution
The configuration loader resolves directories relative to the `WORKSPACE_DIR` environment variable (default: `workspace/default`):
- `Database Path`: `{WORKSPACE_DIR}/softwiki.db`
- `Index Files`: `{WORKSPACE_DIR}/index/`
- `Wiki Exports`: `{WORKSPACE_DIR}/exports/wiki/topics/`

### 4.2 Ingestion & Cleaning
- Import URLs and extract clean article body, stripping navigation headers, ads, and footers.
- Import local PDF files page-by-page.
- Calculate text SHA-256 hash to enforce strict deduplication.

### 4.3 Document-Aware Chunking
- Segments text into overlap-aware chunks.
- Prepends context header metadata to each chunk:
  `[Document: Title | Source: Source Name | Date: YYYY-MM-DD | Section: Section Name]`

### 4.4 CJK-Aware Hybrid Retrieval
- Computes dense embeddings locally using NumPy cosine similarity.
- Tokenizes and index terms using CJK-aware BM25 (splitting CJK symbols into individual characters and English into alphanumeric tokens).
- Combines vector search and BM25 ranks using **Reciprocal Rank Fusion (RRF)**:
  $$RRF\_Score(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$

---

## 5. Relational Database Schema

SQLite schema defined in `softwiki/source_store/models.py`:

```sql
-- Sources metadata mapping
CREATE TABLE sources (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(50),
    url VARCHAR(500),
    trust_level VARCHAR(50),
    source_country VARCHAR(100),
    language VARCHAR(10)
);

-- Ingested raw documents
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(500) NOT NULL,
    url VARCHAR(1000),
    source_name VARCHAR(200),
    source_type VARCHAR(100),
    source_country VARCHAR(100),
    published_at DATETIME,
    collected_at DATETIME,
    language VARCHAR(50),
    author VARCHAR(200),
    raw_text TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    hash VARCHAR(64) UNIQUE NOT NULL,
    trust_level VARCHAR(50),
    topics VARCHAR(500)
);

-- Retrieved units
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    title VARCHAR(500),
    section VARCHAR(200),
    published_at DATETIME
);

-- Extracted claims
CREATE TABLE claims (
    id VARCHAR(100) PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    actor VARCHAR(100) NOT NULL,
    topic VARCHAR(100) NOT NULL,
    stance VARCHAR(50) NOT NULL, -- supportive, cautious, opposed, unclear
    confidence FLOAT NOT NULL,
    published_at DATETIME
);
```

---

## 6. CLI Usage Specifications

To run on a specific workspace, pass the `-w / --workspace` flag (e.g. `-w workspace/my-workspace`):

```bash
# 1. Initialize a workspace
./sw -w workspace/my-workspace init

# 2. Ingest document
./sw -w workspace/my-workspace ingest --url "https://www.example.com/article" --source-id example

# 3. Rebuild search indexes
./sw -w workspace/my-workspace index

# 4. Ask Q&A queries
./sw -w workspace/my-workspace ask "What is the status of the project?"

# 5. Build topic wiki page
./sw -w workspace/my-workspace wiki build --topic topic-alpha
```
