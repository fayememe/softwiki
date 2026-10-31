# System Inputs / Considerations

> **Non-deliverable.** These are system-level inputs (constraints, directions, ideas) that inform design decisions and roadmap trade-offs. They are **not** committed work items and must not be tracked as ✅/☐ tasks. An input becomes a Phase deliverable only through an explicit decision.

## SI-1 — Wiki Generation Prompt System

**Input:** Let managers supply prompts that drive Wiki generation, including content-organization logic (coarse- or fine-grained: homepage, sub-pages, etc.), so users can deeply define the wiki. As the knowledge base updates over time, the wiki must stably conform to the user's definition via those prompts.

**Type:** Direction / architecture input

**Impact:**
- **Gap — not yet covered.** `softwiki/wiki/page_generator.py` hardcodes both system prompts (first-time compiler, incremental updater) and a fixed section layout; there is no per-workspace or per-topic prompt override.
- **Reuse existing mechanism:** workspace-scoped overrides already exist for `scope.md`, `agent_soul.md`/`config/agents.md`, and `workflows.yaml` (deep-merged with `softwiki/templates/`). A wiki prompt/layout config should follow the same template + workspace-override pattern.
- **Touches:** Phase 5 (Wiki manual editing / hybrid mode), incremental Wiki compilation (see `work-log.md` Decision 5), and `docs/02-design/extension-points.md`.

---

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


---

## Workstream — Agent Web（opencode）

> 计划文档：`docs/05-roadmap/agent-web-plan.md`

- 现状：TUI 调用系统 opencode，profile/config/session 隔离，但不是安全沙盒。
- 目标：Web 双模式 —— Quick Answer（AnswerEngine）+ Agent（opencode）。
- L1 已上线：宿主 opencode `:6111` + WebUI Agent 入口；L2 已上线：`/api/agent/*` + Quick/Agent + research steps（非流式）。
- 验证：`/api/agent/status` available；acceptance 11/11；浏览器 Agent 模式已实测。
- 产品化：独立 `softwiki-agent` 容器，pin opencode `1.18.35`，固定配置，升级冒烟测试。


---

## Workstream — Knowledge System

> 原则：`docs/02-design/knowledge-system-philosophy.md`
> 计划：`docs/05-roadmap/knowledge-system-plan.md`

- **P0**：Schema v2（ClaimEvidence/status/Contradiction）、版本 supersede、canonical claim、人工裁定、冲突感知 AnswerEngine。
- **P1**：Graph/Timeline 挂 claim、WikiArtifact stale/rebuild、chunk dedup、Wiki 规模策略。
- **P2**：近重复文档、NLI 冲突检测、自动 family/revision。
- **v0 已完成**：Schema v2、canonical claim + evidence、版本 supersede（新文档）、规则冲突（保守）、Adjudication API/UI、冲突感知 AnswerEngine、WikiArtifact stale/durable rebuild worker/artifact history、chunk dedup、Graph/Timeline claim 回填 + status reproject、metrics。
- 当前：9,766 canonical / 10,573 evidence；1 open conflict（NLI DATA1/DATA2 位重叠）；12 页 Wiki 已重建（stale 0）；Graph 6,994/7,211、Timeline 599/639 已挂 claim；近重复 6 对（仅报告）；worker queue 可用；structured 569 条；MMR + citation check；4 角色 capability mapping + Web/MCP 角色守卫。
- 未完成：Graph/Timeline 版本链与 evidence 多对多、NLI 定时/评测、结构 claim 全量、近重复自动合并、Tier 2。
