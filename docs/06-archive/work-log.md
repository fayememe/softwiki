# softwiki Development & Architecture Decision Work Log

This log records core architectural decisions, technical trade-offs, and business process designs made during the softwiki project's development iterations, for team review and future reference.

---

## 2026-06-07

### Decision 1: Soft Routing Mode Naming Standardization (`wiki-xxxx` namespace)
*   **Background**: To isolate softwiki's working modes from the host terminal opencode's native modes (such as `sisyphus`, `plan`, `build`, etc.), and to allow users to clearly identify when they are in a softwiki-specific research sub-sandbox environment.
*   **Specific changes**:
    *   Renamed the original `study`, `work`, `manage`, `admin` modes with a unified prefix namespace: `wiki-study`, `wiki-work`, `wiki-manage`, and `wiki-admin`.
    *   In the `opencode.json` generator, all built-in opencode agents (e.g., `sisyphus`, etc.) are disabled (`disable: true`), and only custom modes with the `wiki-` prefix are registered.
    *   Updated permission check logic in MCP and FastAPI API service layers for full backward compatibility with new prefixes.

### Decision 2: Edge (Local) vs Cloud LLM Hybrid Architecture
*   **Background**: Addressing the pain points of GraphRAG needing multiple extraction rounds during import, high token consumption during Wiki compilation, slow network speeds, and high API costs.
*   **Specific changes**:
    *   Established a mixed architecture of **"small edge models handle the dirty work, the best cloud model acts as the advisor"**.
    *   Produced [docs/model-guide.md](./model-guide.md) guide.
    *   **Responsibility split**:
        1.  **Embedding**: Fully moved to local (e.g., using `bge-small-zh-v1.5`) to reduce costs.
        2.  **Knowledge extraction**: Uses local small models (e.g., `qwen2.5:7b` on Ollama) or cost-effective cloud APIs (`gpt-4o-mini`) to reduce ingest token costs.
        3.  **QA reasoning**: Uses the most intelligent cloud model (e.g., `Claude-3.5-Sonnet` / `GPT-4o`).
        4.  **Global wiki generation**: Uses ultra-long context models (e.g., `Gemini-2.5-Pro`).

### Decision 3: Backend Multi-Model Configuration Manager (`llm_client.py`)
*   **Background**: After the `model-guide.md` design was completed, to support the system's dynamic resolution and automatic routing of multiple models.
*   **Specific changes**:
    *   Created [llm_client.py](../softwiki/intelligence/llm_client.py) module, supporting reading `configs/model_profiles.yaml` configuration files.
    *   Parses various providers including `openai`, `gemini`, `google`, `ollama`.
    *   Implements automatic assembly and adaptation of API base URL and keys.

### Decision 4: Asynchronous Lazy Extraction Pipeline
*   **Background**: Previously, ingesting a document required synchronous waiting for Claim/Graph/Timeline extraction to complete, causing 10+ second or even minute-long delays for PDF uploads, providing a poor user experience.
*   **Specific changes**:
    *   Added a `status` field (pending, extracting, completed, failed) to the `Document` database table.
    *   Introduced automatic SQLite migration code for backward compatibility with existing databases.
    *   During ingest, chunking, local vectorization, and BM25 index building happen immediately, allowing users to use traditional RAG retrieval right away.
    *   Uses Python `threading` to start a background daemon thread that asynchronously runs the three LLM-dependent extractors, silently updating status to `completed` when done.

### Decision 5: Incremental Wiki Compilation and Update
*   **Background**: As the document library grows, full Wiki page rebuilds cause exponentially increasing token consumption.
*   **Specific changes**:
    *   Refactored `WikiPageGenerator` to introduce incremental diff-patch update logic.
    *   Wiki generation now also produces a `[topic_id].json` file recording all processed Claim IDs.
    *   When new documents trigger Wiki compilation for the same topic, the system compares the database with the JSON file, picks out "new Claims and Timeline events", and feeds "existing Wiki Markdown text" + "new facts" together to the large model, directing it to perform an in-place patch (Incremental Update/Patch), avoiding the expensive cost of full rebuilds.
