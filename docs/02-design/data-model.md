# Data Model

> Design-level reference: all core data models, fields, relationships, and lifecycle in softwiki.
>
> Related docs: [RAG Engine](rag-engine.md) | [Extraction Pipeline](pipeline.md)

---

## Core Models

There are 7 SQLAlchemy ORM models, all defined in `softwiki/source_store/models.py`, using `declarative_base()`.

---

### 1. SourceConfig

**Table name:** `sources`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String(100)` | PK | Source identifier |
| `name` | `String(200)` | NOT NULL | Source name |
| `type` | `String(50)` | | Source type: `official`, `news`, `think_tank`, `academic`, etc. |
| `url` | `String(500)` | | Source URL |
| `trust_level` | `String(50)` | | Trust level: `high`, `medium`, `low` |
| `source_country` | `String(100)` | | Source country/region |
| `language` | `String(10)` | | Language code (e.g., `zh`, `en`) |

SourceConfig is an independent configuration table, not directly foreign-keyed to Document; documents reference sources via the `source_name` field for soft association.

---

### 2. Document

**Table name:** `documents`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Document ID |
| `title` | `String(500)` | NOT NULL | Document title |
| `url` | `String(1000)` | | Original URL |
| `source_name` | `String(200)` | | Source name (soft association with SourceConfig.name) |
| `source_type` | `String(100)` | | Source type snapshot |
| `source_country` | `String(100)` | | Source country snapshot |
| `published_at` | `DateTime` | | Original publication date |
| `collected_at` | `DateTime` | Default `utcnow` | Collection date |
| `language` | `String(50)` | | Document language |
| `author` | `String(200)` | | Author |
| `raw_text` | `Text` | NOT NULL | Raw text (original fetched text) |
| `cleaned_text` | `Text` | NOT NULL | Cleaned text (denoised, normalized) |
| `hash` | `String(64)` | **UNIQUE**, NOT NULL | Content hash for deduplication |
| `trust_level` | `String(50)` | | Trust level inherited from source |
| `topics` | `String(500)` | | Comma-separated topic labels |
| `status` | `String(50)` | Default `completed` | Processing status (see lifecycle) |

**Cascade:** Document cascades Chunk, Claim, Relationship, Event via `cascade="all, delete-orphan"`.

---

### 3. Chunk

**Table name:** `chunks`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Chunk ID |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | Parent document |
| `chunk_index` | `Integer` | NOT NULL | Chunk index (zero-based) |
| `text` | `Text` | NOT NULL | Chunk text content |
| `title` | `String(500)` | | Chunk title (if any) |
| `section` | `String(200)` | | Section name |
| `published_at` | `DateTime` | | Inherited from document |

---

### 4. Claim

**Table name:** `claims`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `String(100)` | PK | Claim ID (UUID string) |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | Source document |
| `text` | `Text` | NOT NULL | Claim text |
| `actor` | `String(100)` | NOT NULL | Actor making the claim |
| `topic` | `String(100)` | NOT NULL | Topic |
| `stance` | `String(50)` | NOT NULL | Stance: `supportive`, `cautious`, `opposed`, `unclear`, etc. |
| `confidence` | `Float` | NOT NULL | Extraction confidence [0, 1] |
| `published_at` | `DateTime` | | Original publication date of the claim's source |

---

### 5. Entity

**Table name:** `entities`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Entity ID |
| `name` | `String(150)` | **UNIQUE**, NOT NULL | Entity name (unique, deduplicated by name) |
| `type` | `String(100)` | | Entity type: `person`, `organization`, `place`, `topic`, `concept`, etc. |
| `description` | `Text` | | Entity description |

Entity is not directly foreign-keyed to Document; it is indirectly referenced through Relationship's `source_name` / `target_name` fields.

---

### 6. Relationship

**Table name:** `relationships`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Relationship ID |
| `source_name` | `String(150)` | NOT NULL | Source entity name (soft association with Entity.name) |
| `target_name` | `String(150)` | NOT NULL | Target entity name (soft association with Entity.name) |
| `relation_type` | `String(100)` | NOT NULL | Relationship type (e.g., `works_at`, `located_in`) |
| `description` | `Text` | | Relationship description |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | Evidence document |
| `confidence` | `Float` | Default `1.0` | Extraction confidence [0, 1] |
| `published_at` | `DateTime` | | Publication date of evidence |

---

### 7. Event

**Table name:** `events`

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | PK, autoincrement | Event ID |
| `title` | `String(250)` | NOT NULL | Event title |
| `description` | `Text` | | Event description |
| `event_date` | `DateTime` | NOT NULL | Event date |
| `topic` | `String(100)` | | Topic |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | Evidence document |
| `confidence` | `Float` | Default `1.0` | Extraction confidence [0, 1] |

---

## Model Relationship Diagram

```
SourceConfig (sources)
  │
  │  Soft association (source_name)
  ▼
Document (documents) ──┬──cascade──▶ Chunk (chunks)
  │                    ├──cascade──▶ Claim (claims)
  │                    ├──cascade──▶ Relationship (relationships)
  │                    └──cascade──▶ Event (events)
  │
  │  Soft association (source_name / target_name)     Entity (entities)
  │         ┌──────────────────────────────────────┘
  ▼         ▼
Relationship (relationships)
```

### Key Design Decisions

| Decision | Explanation |
|---|---|
| **Entity ↔ Relationship name-based association** | Entity and Relationship have no foreign key between them; instead they use `Entity.name` ↔ `Relationship.source_name` / `Relationship.target_name` for name matching. This allows entities extracted from multiple documents to merge naturally, avoiding cross-document ID coordination issues. |
| **Document cascade delete** | Document's `cascade="all, delete-orphan"` ensures deleting a document automatically cleans up its Chunk, Claim, Relationship, and Event records. All foreign keys have `ON DELETE CASCADE`. |
| **Soft association vs foreign keys** | SourceConfig→Document is soft-associated via the `source_name` string, not a foreign key. This decouples Document from the existence of a SourceConfig record, enabling independent collection and backfilling. |
| **Claim uses String PK** | Claim's `id` is a UUID string (`String(100)`), suitable as a cross-system reference identifier, avoiding integer auto-increment ID conflicts in distributed scenarios. |

---

## Document Lifecycle

The Document `status` field records processing state, driven by the extraction pipeline (`softwiki/extraction/processor.py`):

```
┌─────────┐
│ pending │ ◄── Initial state (background=True enqueued)
└────┬────┘
     │
     ▼
┌───────────┐
│ extracting│ ◄── Background thread or sync call starts processing
└─────┬─────┘
     │
     ├── success ──▶ ┌───────────┐
     │               │ completed │
     │               └───────────┘
     │
     └── failure ──▶ ┌────────┐
                     │ failed │
                     └────────┘
```

| Status | Meaning | Set When |
|---|---|---|
| `pending` | Document stored, awaiting extraction | When `run_extraction_pipeline()` is called with `background=True` |
| `extracting` | Extraction in progress | At start of `_bg_extraction_worker()` or synchronous `run_extraction_pipeline()` |
| `completed` | All extractions done | After all extraction steps (Claim, Graph, Timeline) succeed |
| `failed` | Extraction failed | When any step throws an exception, set in the `except` block |

> **Note**: In direct (non-background) mode, the default status is `completed` because extraction finishes synchronously. The `pending`→`extracting` transition only occurs in async background mode.

---

<!-- 
  This file contains data model definitions only.
  Query/RAG logic → rag-engine.md
  Extraction pipeline details → pipeline.md
-->
