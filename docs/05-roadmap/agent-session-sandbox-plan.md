# Agent Session / 用户沙盒 / 审核入库 计划

> status: 🚧 讨论中（2026-10-24）
> 目标：让 Agent 具备“可管理的会话 + 用户沙盒 + 人工审核入库”，当前单用户可跑，未来可扩展到多用户。
> 非目标：本期不做完整登录/RBAC/多租户隔离；不做自动入库。

---

## 1. 用户要什么

1. Agent 上有比较丰富的 session 应用（列表、续聊、重命名、删除、搜索）。
2. 现在没有用户系统（单用户），但未来要能扩展。
3. session 跟着用户走。
4. 用户可以把 Markdown 存到自己的沙盒。
5. 沙盒内容可以入库，但**不是自动**，也**不是所有用户都能直接入库**。
6. 用户可以“提交审核入库”。

---

## 2. 现状（代码事实）

| 项 | 现状 |
|---|---|
| SoftWiki Chat session | 只存在浏览器 `localStorage`（`softwiki_sessions`），不跟用户走 |
| Agent session | opencode 自己的 session，存在 `.softwiki_runtime/<ws>_<hash>/` 的 XDG_DATA_HOME |
| Agent 模式 | `wiki-research` 只读；`bash`/`edit`/`ingest`/`index`/`wiki_build` 全部 deny |
| 用户系统 | `User` / `WorkspaceMember` 表和 auth 代码已有，但 `SOFTWIKI_AUTH_ENABLED` 默认关闭 |
| 沙盒 | 不存在 |
| 审核队列 | 不存在 |
| Markdown 入库 | API `/api/ingest/file` 有 `.md` 分支，但当前主要面向上传；需要补 chunk/index/审核元数据 |

---

## 3. 核心设计

### 3.1 身份抽象（现在单用户，未来多用户）

新增一个轻量 `current_user()`：

- 现在：固定返回 `local`（或 `wiki-admin` 的单用户身份）。
- 未来：从 auth middleware 的 `request.state.user` 取 `user_id`。
- 所有 session / sandbox / review 记录都带 `owner_id`，**不要**把用户身份写死到目录结构之外。

### 3.2 Session 模型

推荐：**SoftWiki 存“归属 + 标题 + 元数据”，opencode 存消息正文**。

新增表 `agent_sessions`：

| 字段 | 说明 |
|---|---|
| `id` | SoftWiki session id |
| `owner_id` | 现在 `local`，未来 user id |
| `workspace` | `kb-alpha` 等 |
| `opencode_session_id` | opencode 的 session id |
| `title` | 用户可改 |
| `created_at` / `updated_at` | 列表排序 |
| `archived` | 软删除 |

Agent 列表、续聊、重命名、删除都走 SoftWiki API；opencode 仍是消息 source of truth。

多用户注意：

- 不能所有用户共用一个 opencode session 列表。
- 方案 A：每个用户独立 `XDG_DATA_HOME` + 独立 opencode runtime（隔离最好，成本高）。
- 方案 B：一个 opencode server，SoftWiki 用 `agent_sessions.owner_id` 过滤；需要防止 session id 越权（API 代理必须校验 owner）。
- 当前单用户先用 B；多用户再评估 A。

### 3.3 用户沙盒

路径建议：

```text
workspace/<workspace>/sandbox/<owner_id>/
  notes/
  drafts/
  attachments/
  .meta/
```

- 只允许写 `sandbox/<owner_id>/`；不能写 KB、配置、其他用户目录。
- Agent 通过 **MCP 工具**写沙盒，而不是开放 `edit`/`bash`：
  - `sandbox_list(path?)`
  - `sandbox_read(path)`
  - `sandbox_write(path, content)`（只允许 `.md` / `.txt`）
  - `sandbox_submit(path, note, topics?)`
- `wiki-research` 权限：允许 sandbox 工具 + KB 只读；仍然 deny `ingest`/`index`/`wiki_build`。
- 沙盒内容**不会**自动进索引。

### 3.4 审核队列

提交后进入：

```text
workspace/<workspace>/review/<submission_id>/
  submission.json   # owner, source_path, note, topics, status, timestamps
  content.md        # 快照，避免用户后续改文件
```

状态：

- `pending`
- `approved`
- `rejected`
- `needs_changes`

工具/API：

- 用户：`sandbox_submit`
- 管理员/管理角色：`review_list`、`review_approve`、`review_reject`
- 审批通过：
  1. scope_guard 检查
  2. 去重（hash / URL）
  3. 以 `source_type=sandbox`、`source_name=<owner>` 入库
  4. 切 chunk + embedding + BM25（增量，或复用现有 index 流程）
  5. 写审计 JSONL
- **Agent 不能调用 approve**；只有 `wiki-manage` / `wiki-admin` 可以。

### 3.5 权限矩阵

| 能力 | wiki-study | wiki-work | wiki-manage | wiki-admin |
|---|---|---|---|---|
| KB 只读 | ✅ | ✅ | ✅ | ✅ |
| 写自己沙盒 | ✅ | ✅ | ✅ | ✅ |
| 提交审核 | ✅ | ✅ | ✅ | ✅ |
| 查看审核队列 | ❌ | ❌ | ✅ | ✅ |
| 批准/拒绝 | ❌ | ❌ | ✅ | ✅ |
| 直接 ingest/index | ❌ | ❌ | ✅ | ✅ |

当前单用户实例按 `wiki-admin` 使用；矩阵先落代码，不强制登录。

---

## 4. 分阶段

### P0（单用户，最小可用）

- [ ] `current_user()` 抽象（固定 `local`）
- [ ] 沙盒目录 + `sandbox_list/read/write/submit` MCP 工具
- [ ] 审核目录 + `review_list/approve/reject` MCP 工具
- [ ] 审批通过复用 Markdown 入库 + 增量索引
- [ ] Agent prompt 增加“可保存到沙盒 / 提交审核”说明
- [ ] 验收：Agent 写 `sandbox/local/notes/pl031.md` → submit → review approve → KB 可检索

### P1（WebUI session app）

- [ ] `agent_sessions` 表 / 或先代理 opencode `GET /session`
- [ ] Sidebar “Agent Sessions”：列表、新建、续聊、重命名、删除
- [ ] `GET/PATCH/DELETE /api/agent/session/*`
- [ ] 审核面板：pending 列表 + 预览 + approve/reject
- [ ] 单用户先显示全部；多用户按 owner 过滤

### P2（多用户）

- [ ] auth 启用 + `owner_id` 全链路
- [ ] 每用户独立 opencode runtime 或 session ACL
- [ ] 沙盒配额 / 审计 / 越权测试
- [ ] 审核角色绑定 `WorkspaceMember.role`

---

## 5. 需要确认的决策

1. 沙盒路径用 `workspace/<ws>/sandbox/<owner>/` 还是 `workspace/<ws>/users/<owner>/sandbox/`？
2. 当前单用户的 `owner_id` 用 `local` 还是 `wiki-admin`？
3. P0 审核先做 MCP/API，还是同时做 WebUI 审核面板？
4. Markdown 入库走“直接调用入库服务”还是“复用 `/api/ingest/file` + `/api/index`”？
5. 多用户 session 用“独立 runtime”还是“共享 server + owner 过滤”？

## 6. 推荐

先做 **P0 + P1 的 session 列表**：

- 单用户即可验证“Agent 写沙盒 → 提交 → 管理员批准 → KB 检索”闭环；
- Session 列表直接代理 opencode，先不做新表，减少迁移；
- 多用户再引入 `owner_id` 和独立 runtime。

这样不会阻塞当前 demo，也为未来的用户系统留好接口。
