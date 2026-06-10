# System Dependencies & Environment Guide

This document lists all system-level and library-level dependencies required to run the `softwiki` engine in development and production environments.

---

## 1. Core Runtime Environment

| Dependency | Minimum Version | Recommended | Notes |
|---|---|---|---|
| **Python** | `>= 3.10` | `3.14.x` | Core backend programming language. |
| **Node.js** | `>= 18.x` | `20.x (LTS)` | Required for running the Web Frontend dashboard (Next.js). |
| **npm** | `>= 9.x` | `10.x` | Node.js package manager (yarn / pnpm are also supported). |
| **Docker** | `>= 20.10` | `24.x` | Required to host databases (Neo4j, Qdrant, PostgreSQL, Redis) via Docker Compose. |
| **Docker Compose** | `>= 2.0` | `2.20+` | Orchestrates backend services. |

---

## 2. Backend Python Libraries

These libraries are defined in [pyproject.toml](../pyproject.toml) and are automatically installed when setting up the virtual environment:

### Core Package Dependencies:
- **`numpy` (>=1.24.0)**: Used for calculating Cosine Similarity of vectors in the local vector store. Bypasses the need for binary databases for small/medium datasets.
- **`rank-bm25` (>=0.2.2)**: Pure-python BM25 BM25Okapi implementation for lexical keyword search.
- **`sqlalchemy` (>=2.0.0)**: Object-Relational Mapping (ORM) to handle SQLite database transactions.
- **`click` (>=8.0.0)**: Command-line interface builder for our `./sw` script.
- **`pydantic` (>=2.0.0)**: Data validation and schema settings.
- **`openai` (>=1.0.0)**: SDK to interact with OpenAI API or compatible endpoints (DeepSeek, Groq, local LLMs) for claim extraction and RAG answer synthesis.
- **`pypdf` (>=3.0.0)**: Extracts plain text and metadata page-by-page from local PDF files.
- **`beautifulsoup4` (>=4.11.0)** & **`requests` (>=2.28.0)**: Scrapes HTML articles and parses metadata tags (like author, publish date) from web URLs.
- **`fastapi` (>=0.100.0)** & **`uvicorn` (>=0.20.0)**: Used in later phases to run the HTTP REST API.

---

## 3. Storage & Database Services (Dockerized)

For larger setups, Phase 3 (Neo4j Graph) and Phase 4 (Scale), the following databases are recommended. They run inside Docker, meaning you do **not** need to install them directly on your host machine:

### 3.1 Neo4j (Graph Database)
- **Role**: Stores entities (e.g. Country, Policy, Event) and relationship edges (e.g. SUPPORTS, OPPOSES, MEMBER_OF) to run GraphRAG.
- **Docker Image**: `neo4j:5.x` (Community or Enterprise edition).
- **Default Ports**: `7474` (HTTP Admin Console), `7687` (Bolt binary protocol for code connection).

### 3.2 Qdrant (Vector Database)
- **Role**: Production-grade vector database that replaces the local NumPy vector file once document count exceeds thousands of entries.
- **Docker Image**: `qdrant/qdrant:latest`
- **Default Ports**: `6333` (REST HTTP API), `6334` (gRPC interface).

### 3.3 PostgreSQL (Document Database)
- **Role**: Stores metadata, raw/cleaned text bodies, and claims at scale.
- **Docker Image**: `postgres:16-alpine`
- **Default Ports**: `5432`

### 3.4 Redis (Caching & Task Queue)
- **Role**: Cache storage and background task broker (using Celery or RQ) for large-scale async crawling and extraction.
- **Docker Image**: `redis:7-alpine`
- **Default Ports**: `6379`

---

## 4. Frontend Dependencies (Web Dashboard)

The web dashboard is built using **Next.js** (React) and resides in the `web/` directory.

### Key package.json dependencies:
- **`next` (>=14.x)**: React Framework with Server-Side Rendering (SSR).
- **`react` (>=18.x)** & **`react-dom` (>=18.x)**: UI render engine.
- **`cytoscape`** or **`vis-network`**: Javascript libraries used in the Web UI to visualize the Neo4j entities and claims graph in 2D.
- **`tailwindcss`**: Utility-first CSS framework for visual aesthetics (dark mode, glassmorphism, responsive grid layouts).
- **`lucide-react`**: Vector icons for the dashboard sidebar and status panels.
