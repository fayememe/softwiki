# SoftWiki Feature Todo List

> 记录待实现的功能想法，不分优先级，随时补充。
> 实现时移入对应 milestone 或 project-status.md。

---

## 模块开关 & 部署 Profile

**背景**：不同规模的知识库需要不同的功能组合，避免小知识库跑全家桶。

- [ ] 将 `web_search` 纳入 `ENABLED_MODULES`，与五层知识引擎统一管理（目前用独立 env `SOFTWIKI_ENABLE_WEB_SEARCH`）
- [ ] 定义预设 profile，通过 `SOFTWIKI_PROFILE=lite|standard|full|search` 快速配置：

  | Profile | ENABLED_MODULES | 说明 |
  |---|---|---|
  | `lite` | `rag,llmwiki` | 个人小知识库，极简快速 |
  | `standard` | `rag,claimdb,llmwiki` | 中型，加立场追踪 |
  | `full` | `rag,graph,claimdb,timeline,llmwiki` | 大型企业全家桶 |
  | `search` | `rag,llmwiki,web_search` | 服务端搜索，供瘦客户端使用 |

- [ ] `config.py` 的 `is_module_enabled()` 支持 profile 展开逻辑

---

## GraphRAG 升级

- [ ] 集成 **LightRAG** 替换当前简单的 SQLite 图谱实现
  - 当前：LLM 抽取 Entity/Relationship → SQLite → SQL LIKE 过滤（无多跳推理）
  - 目标：LightRAG 增量 insert + 真正图遍历 + 全局/局部检索
  - 保留现有 Entity/Relationship 表作为兼容层或迁移路径
  - LightRAG 增量更新友好，适合我们的逐文档入库模式

---

## Token / RBAC（Phase 3）

**背景**：不同用户看到不同的模式，mode 约束从 honor system 升级为正式 token 机制。

- [ ] Token 文件（`~/.softwiki/token` 或 workspace 内）— 记录用户身份和允许的 modes
- [ ] Shell 启动时读 token，只暴露允许的 modes，拒绝越权
- [ ] MCP server 也验 token（写操作二次校验）
- [ ] Token schema：`{ subject, role, workspace_scope, allowed_modes, expires_at }`
- [ ] 示例场景：
  - 用户 A（admin token）→ 全部 4 个 mode
  - 用户 B（work token）→ 只能进 wiki-work
  - 用户 C（study token）→ 只能进 wiki-study

---

## 远程 MCP（Phase 2）

- [ ] MCP server 支持 HTTPS + Bearer token 远程访问
- [ ] Shell 的 `_call_mcp_tool()` 替换传输层（本地 stdio → 远程 HTTP）
- [ ] 本地 stdio-to-remote bridge（`softwiki mcp bridge --url ...`）
- [ ] 文档：如何在 Claude Desktop / Cursor 配置远程 softwiki MCP

---

## index() 增量优化

- [ ] `index()` 目前全量重建（delete all + recreate），改为只处理新增/变更文档
- [ ] 文档加 `indexed_at` 时间戳，增量 index 只处理 `indexed_at < updated_at` 的文档
- [ ] BM25 增量：目前 `add_documents()` 仍需重建整个 BM25 模型（IDF 依赖全语料）；考虑定期批量重建策略

---

## wiki-work Submit 流程

**背景**：wiki-work 用户研究产出不能直接 ingest，需要暂存给 manage 用户审阅。

- [ ] 定义 staging 目录结构（`workspace/staging/<session-id>/`）
- [ ] wiki-work 用户的 `submit` workflow：写结构化研究笔记到 staging
- [ ] wiki-manage 用户的审阅命令：`./sw review` 列出 pending submissions
- [ ] 审阅通过 → 正式 `softwiki_ingest`，不通过 → 退回并注明原因
- [ ] MCP tool：`softwiki_submit`（work 权限）、`softwiki_review`（manage 权限）

---

## WebUI

- [ ] `web/` 目录已有 Next.js 框架，补完核心功能
- [ ] 关键面板：ChatPanel / IngestPanel / DocumentsPanel / ClaimsPanel / WikiPanel
- [ ] 通过 REST API（`softwiki/api/server.py`）连接 Core，不直接访问 DB

---

## 其他

- [ ] `mcp` 包加入 `pyproject.toml` 正式依赖（目前未列入）
- [ ] `ingestion/web_loader.py` 升级：BeautifulSoup 对复杂页面效果有限，考虑 Readability.js 或 Jina AI Reader
- [ ] 测试覆盖率提升：extraction / wiki / answer_engine 模块缺少测试
