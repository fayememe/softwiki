# Project Status

## Sprint — Chat-Style QA + WebUI Workspace Switching

- ✅ Answer engine question classification — three-way split: chat/admin query/knowledge QA
- ✅ Chat handling — casual conversation (greetings, thanks, farewell) natural responses in English
- ✅ Admin query handling — "what's in the knowledge base" directly queries DB stats (in English)
- ✅ Backend API: GET /api/workspaces — list available workspaces
- ✅ Backend API: POST /api/workspace — switch workspace at runtime
- ✅ Backend API: /api/status supports ?workspace= parameter to preview other workspaces
- ✅ Frontend api.ts — apiListWorkspaces / apiSwitchWorkspace / apiStatus(workspace?)
- ✅ Frontend page.tsx — workspace state management + localStorage persistence
- ✅ Frontend Sidebar — three-layer layout rewrite (Workspace / Tools / Sessions)
- ✅ Frontend Sidebar CSS — LobeChat-style dark/light themes
- ✅ Frontend ChatMessage — message bubble style upgrade
- ✅ Frontend ChatPanel — input field rounded corners + focus highlight

## Sprint — Conversation Memory

- ✅ Backend AskRequest + history field
- ✅ AnswerEngine receives historical messages for LLM injection
- ✅ Frontend ChatPanel sends last 20 messages

Current workspace: default (0 documents) / eva-kb (30 documents, 2173 claims, 1157 entities, 2000 relationships, 607 events)

## Phase 1 — Core Knowledge Engine

- ✅ Document ingestion — URL + PDF, SHA-256 dedup, multi-language
- ✅ Five-layer knowledge extraction — Claim / Entity-Relationship / Timeline / RAG / LLM-Wiki
- ✅ Hybrid retrieval — dense + BM25, RRF fusion
- ✅ RAG answer engine — 5-layer context fusion, citation management
- ✅ MCP service foundation — 17 tools, stderr-protected JSON-RPC
- ✅ CLI — init/ingest/index/ask/wiki/shell/api
- ✅ Shell TUI — opencode wrapper, zero core dependency
- ✅ Workspace isolation — WORKSPACE_DIR any path, fully independent
- ✅ Scope guard — scope.md-driven knowledge base scope check

## Phase 2 — Graph Enhancement + Image Support + WebUI

- ☐ Image attachment system — inline image upload, storage, reference in md/wiki
- ☐ Image serving — Wiki reader / proxy-accessible image resources
- ☐ Chart OCR — extract text from complex chart images into index
- ☐ Image search — retrieve by image content/description

- ✅ LightRAG integration — BFS traversal, 6 query modes, incremental insertion
- ✅ Storage backend abstraction — JSON / PostgreSQL config switch
- ✅ LLM/Embedding separation — independent provider configuration
- ✅ Dimension safety check — auto-block on embedding model change
- ✅ WebUI redesign — dark theme, Plus Jakarta Sans font
- ✅ Session management — create/switch/delete/rename, localStorage persistence
- ✅ Wikipedia reader — Linux Libertine font, TOC sidebar
- ✅ Theme switching — Dark / Light / Auto cycle
- ✅ MCP tool expansion — 17 tools (+lightrag_query/explore/status)
- ✅ Architecture documentation — 18 documents across six categories

## Phase 3 — Remote Access

- ☐ Remote MCP — HTTPS + Bearer token
- ☐ swshell standalone client — zero core dependency, HTTP MCP to remote
- ☐ index() incremental mode — full rebuild → only process new documents

## Phase 4 — Permissions & Multi-User

- ☐ Token/RBAC — formal token mechanism binding role + workspace
- ☐ wiki-work submit flow — staging → review → publish
- ☐ Audit log — traceable MCP operations

## Phase 5 — Wiki Manual Editing + Standalone Site

- ☐ Topic Editor — visual add/delete/edit topics, groups, synonyms, no YAML needed
- ☐ Wiki hybrid mode — auto-generated + manual markdown override, AI only fills gaps without overwriting existing content
- ☐ Wiki page editor — inline page markdown editing, rebuild on save
- ☐ Wiki standalone deployment — split read-only Wiki site from Dashboard, externally accessible
- ☐ Wiki static export — compile markdown to static HTML, serve via Nginx

- ☐ Topic Editor — visual add/delete/edit topics, groups, synonyms, no YAML needed
- ☐ Wiki hybrid mode — auto-generated + manual markdown override, AI only fills gaps without overwriting existing content
- ☐ Wiki page editor — inline page markdown editing, rebuild on save

## Phase 6 — Deployment & Quality

- ☐ WebUI responsive — mobile adaptation
- ☐ web_loader upgrade — Readability.js / Jina AI Reader
- ☐ Test coverage — extraction / wiki / answer_engine
- ☐ Docker deployment stack — docker-compose one-click launch
