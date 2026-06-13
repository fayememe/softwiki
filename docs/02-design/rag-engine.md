# RAG Engine Design

## Hybrid Search

`HybridSearcher` (`softwiki/rag/hybrid_search.py`) combines dense and sparse retrieval via Reciprocal Rank Fusion (RRF).

### Dense: `LocalVectorStore`

- Uses NumPy-based cosine similarity search.
- Query is embedded via `WikiEmbedder.embed_query()`.
- Returns top-`k*2` candidates (oversampled for fusion).

### Sparse: `Bm25Store`

- Uses `rank-bm25` (BM25Okapi) with CJK-aware tokenization.
- Raw query string is passed directly.
- Returns top-`k*2` candidates.

### Fusion: RRF

Reciprocal Rank Fusion merges the two ranked lists:

```
score(chunk) = Σ 1 / (k + rank_i)
```

Where:
- `k = 60` (constant, softens rank weighting)
- `rank_i` is the zero-based position in each result list
- Scores are summed per chunk ID across both dense and sparse results

The top-`k` chunks by RRF score are fetched from the database via `DocumentRepository.get_chunks_by_ids()`, and each result pair includes the chunk, its parent document, and the fusion score.

```python
# From HybridSearcher.search():
for rank, res in enumerate(vector_results):
    cid = res["chunk_id"]
    rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (60 + rank + 1)

for rank, res in enumerate(bm25_results):
    cid = res["chunk_id"]
    rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (60 + rank + 1)
```

Returns `List[Dict]` with keys `chunk`, `document`, and `score`.

---

## 5-Layer Context Fusion

`AnswerEngine.ask()` (`softwiki/intelligence/answer_engine.py`) builds a consolidated prompt from up to 5 knowledge layers. Each layer is independently gated by `is_module_enabled()`.

### Layer 1: RAG (Hybrid Search)

- Calls `HybridSearcher.search(db, question, top_k=5)`.
- Each result chunk is formatted with a citation marker and document metadata, then appended to the context block.

### Layer 2: ClaimDB

- Extracts words longer than 3 characters from the question.
- Runs a SQL `LIKE` query against the `Claim` table, matching on any of the extracted words.
- Returns up to 10 matching claims with actor, stance, text, date, and confidence.

### Layer 3: Graph

- Attempts a **LightRAG** query first (via `_try_lightrag_query()`). If LightRAG credentials are configured and a result is returned, those lines are used directly.
- **Fallback**: SQL `LIKE` on the `Relationship` table, matching `description`, `source_name`, or `target_name` against question words.

### Layer 4: Timeline

- SQL `LIKE` on the `Event` table, matching `title` or `description` against question words.
- Results are ordered by `event_date ASC`, limited to 10.

### Layer 5: LLM Wiki

- Reads compiled markdown wiki pages from disk (`<export_dir>/wiki/topics/`).
- A wiki page is included if its filename (without `.md`) is a substring of the question (lowercased, hyphens replaced with spaces).
- Each page is truncated to 800 characters.

### Consolidation

All enabled layers are assembled into a single `consolidated_context` string with section headers:

```
### Relevant Text Excerpts (RAG):
...
### Extracted Claims (ClaimDB):
...
### Knowledge Graph Relationships (Graph):
...
### Chronological Events (Timeline):
...
### Existing Topic Synthesis (llm-wiki):
...
```

If no layer produced context, a fallback message is returned: *"No relevant sources found in active modules to answer this question."*

### LLM Prompting

The consolidated context is sent to an LLM (configured via `get_llm_client_and_params("high_quality_analysis")`) with a structured system prompt enforcing:

- Inline source citations (`[1]`, `[2]`, etc.)
- No unsupported conclusions
- Distinction between official positions, news reporting, and speculation
- A confidence level assessment (High/Medium/Low)

If no LLM client is available, `_generate_fallback_answer_modular()` produces a local rule-based answer with all retrieved segments listed.

---

## Citation Management

`CitationManager` (`softwiki/rag/citations.py`) tracks document-level citations across a single answer session.

- **Deduplication**: A `doc_id_to_num` dict maps document IDs to their sequential citation number. If the same document appears multiple times, the same `[n]` is reused.
- **Assignment**: `get_citation_num(doc_id, metadata)` assigns the next available number for a new document and stores the reference metadata.
- **Rendering**: `render_citations()` produces a footnotes block:

```
### Sources & Citations
[1] SourceName. "Title" (2025-01-01). Available at: https://...
[2] ...
```

Citations are appended to the final answer string (both LLM-generated and fallback).

---

## Scope Guard

`scope_guard.py` (`softwiki/intelligence/scope_guard.py`) enforces knowledge-base scope boundaries.

### `check_scope(text, item_type) -> (bool, str)`

**Lookup order** for `scope.md`:

1. `<workspace_dir>/scope.md`
2. `<workspace_dir>/config/scope.md`

**Fallback behavior**: If no `scope.md` exists, the function returns `(True, "No scope.md defined, bypassing check.")` — meaning **all content is accepted**.

**LLM-based check** (when `scope.md` exists):

1. Reads `scope.md` content.
2. Calls an LLM (preferring the `cheap_extraction` profile, falling back to `high_quality_analysis`) with a system prompt that defines the scope policy.
3. The LLM responds with `IN_SCOPE: <reason>` or `OUT_OF_SCOPE: <reason>`.
4. Parsing logic also handles free-form "out of scope" text as a fallback.

**Error handling**: If the LLM call fails, the check is bypassed (returns `(True, "LLM error: ...")`) with a warning printed to stderr.

### Usage

Scope guard is invoked before ingestion and query execution. If the result is `(False, reason)`:
- **Ingest**: The document is rejected with a user-facing explanation.
- **Query**: The query is rejected before any retrieval occurs.

This prevents the knowledge base from drifting outside its intended subject area.
