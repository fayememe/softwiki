# WebUI Guide

## Launch

```bash
./sw api                    # REST API @ :8000
cd web && npm run dev       # Frontend @ :3000 (optional)
```

`./sw api` starts the backend API service while also hosting the WebUI static pages. Visit `http://localhost:8000` to use.

To run the frontend in development mode (hot reload), open another terminal and run `npm run dev`, then visit `http://localhost:3000`.

## Panels

### ChatPanel — Research QA

RAG (Retrieval-Augmented Generation) chat interface. Enter a research question and the system searches across full-text, vector index, claim database, and knowledge graph to generate an answer with source citations.

- **Source citations**: Each answer lists citation sources at the bottom; click to expand the SourceDrawer sidebar showing source metadata, relevant excerpts, and original links
- **Suggested questions**: Pre-defined question entry points on empty chat for one-click asking
- **Session operations**: Clear session, Enter to send, Shift+Enter for newline
- **Status display**: Shows error guidance when API is unavailable

### IngestPanel — Source Ingestion

Supports two ingestion modes:

- **Web URL**: Input a web link to ingest text content
- **PDF File**: Drag-and-drop or click to upload a PDF file

Optional Source ID field matches source configuration in `configs/sources.yaml`. Claims are automatically extracted after successful ingestion.

Action buttons:

- **⊕ Ingest Document**: Execute ingestion
- **⟳ Rebuild Index**: Rebuild vector + BM25 full-text index (required after ingestion to search new content)

The Activity Log at the bottom shows real-time logs of all operations.

### DocumentsPanel — Ingested Documents

Displays a table of all ingested documents:

| Field | Description |
|---|---|
| Title | Document title with original link (if available) |
| Source | Source name (e.g., wikipedia, reuters) |
| Type | Source type (web / pdf / manual) |
| Published | Publication date |
| Trust Level | Trust indicator (high / medium / low) |
| Actions | Delete button (cascade deletes associated chunks, claims, events, relationships after confirmation) |

### ClaimsPanel — Claims & Assertions

Displays structured claims automatically extracted from ingested documents:

| Field | Description |
|---|---|
| Actor | Claim subject (person/organization) |
| Topic | Topic label |
| Stance | Stance classification: Supportive / Cautious / Opposed / Unclear |
| Confidence | Confidence percentage |
| Claim Description | Original claim text |
| Date | Publication date |

Two filters at the top:

- **Actor**: Filter by subject (dropdown, auto-aggregates all appearing actors)
- **Stance**: Filter by stance (Supportive / Cautious / Opposed / Unclear)

### WikiPanel — Wikipedia-Style Reader

Compiles knowledge base content into structured Wiki pages.

Three-column layout:

- **Left column Topics**: List of all available topics, click to switch
- **Center column Article**: Markdown-rendered Wiki body with inline table of contents
- **Right column TOC**: Sticky table of contents sidebar, auto-highlights current section on scroll

Actions:

- **◆ Compile Wiki Page**: First-time compilation of selected topic
- **↻ Rebuild**: Recompile (use after data updates)
- IntersectionObserver auto-tracks active sections during scroll

## Session Management

Left sidebar Sessions area:

- **Create**: Click the `+` button to create a new session
- **Switch**: Click a session item to activate
- **Delete**: Hover shows the `✕` button
- **Rename**: Double-click the session name to edit, Enter to confirm, Escape to cancel
- **Auto-naming**: Automatically names the session after the first message's question text
- **Persistence**: Session data (including message history) is auto-saved to browser `localStorage`

The sidebar top navigation switches between Chat / Ingest / Documents / Claims / Wiki panels. Documents and Claims panels show count badges.

## Theme Switching

Floating button in the top-right corner, cycles through:

Dark（🌙）→ Light（☀️）→ Auto（◐）→ Dark…

- Setting is saved to `localStorage`, persists across refreshes
- Auto mode listens to system `prefers-color-scheme`, responds to system theme changes in real time
