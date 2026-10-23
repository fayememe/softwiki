# 试用就绪清单（Trial Readiness）

> 目标：**单校、单实例、自部署、试用评估**。不是正式生产。
> 验收方式：学校在一台干净的内网机器上跑完第 2 节的 10 步。

---

## 0. 边界

- 一个学校 = 一个实例；不做多租户、跨校。
- 一个实例 = 多个 workspace（科研 / 课程 / 图书馆 / 行政）。
- 一个管理员 + 普通账号；不做 SSO。
- 先做 2 个深模板：**研究报告**、**课程问答**；行政库用默认模板。
- wiki 在试用阶段**只读**，不回写（adjudication = off）。
- 不做：集群、高可用、移动端、10 个学科、通用工作流 DSL、完整 RBAC 矩阵。

---

## 1. 当前基线（2026-10-23 实测）

| 项 | 结果 |
|---|---|
| venv editable 指向 | `/home/faye/mydrv/git/softwki`（错误路径）→ 已用 `pip install -e . --no-deps` 修正 |
| `import softwiki.mcp.server` | 现在解析到本仓库 |
| `tests/test_mcp.py` 收集 | 失败：缺 `softwiki_search` 别名 → 已补 `softwiki_search` / `softwiki_ask` |
| 全量 `pytest tests` | **挂起**（>120s 未结束），疑似 embedding/LLM 网络调用；不能作为基线 |
| 测试规模 | 9 个文件；`test_answer_engine` 仍在断言已不存在的 `Direct Answer` / `Evidence Summary` |
| PDF | 仓库内 0 个 PDF；loader 仅用 `pypdf` 抽文本，无 OCR |
| 页码 | `Chunk` 无 page/offset 字段；引用无法定位页码 |
| 引用 | 仅 RAG 有 `[n]`；claims/graph/timeline/wiki 是裸文本 |
| scope | `AnswerEngine.ask` 未调用 scope guard |
| 认证 | 无；API/MCP 没有 token/登录 |
| workspace 隔离 | 进程级 `os.environ["WORKSPACE_DIR"]`，全局切换 |
| 报告 | 无接口、无任务队列；`exports/wiki/reports` 是空目录 |
| 部署 | 无 Dockerfile、无 compose |
| MCP transport | 未提交的 sse + streamable-http + both 改造；DNS rebinding 保护已关闭 |

---

## 2. 试用验收脚本（10 步）

1. `docker compose up`，打开地址，管理员登录；
2. 建两个 workspace（research / course），分配用户；
3. 上传 20 篇真实 PDF 到科研库、10 篇课程材料到课程库；
4. 问 5 个问题，每个引用都能定位到**页码/段落**；
5. 问一个库外问题，**明确拒答**；
6. 问一个来源冲突的问题，**呈现分歧**；
7. 生成一份报告并下载，含方法、局限、引用；
8. 同一份报告重跑一次，**证据集与 manifest 一致**；
9. 两个用户在不同 workspace 并发使用，**不串库**；
10. 备份 → 清空 → 恢复，数据与引用完整。

映射：1/7/8/10 → P1；2/3/4/5/9 → P0；6 → P1（模板 + verifier）。

---

## 3. P0 任务（试用阻塞项）

### T0 — 环境与测试基线

- [x] 修正 venv editable 指向本仓库
- [ ] 清理 `tests/__pycache__`（旧 `.pyc` 的 `co_filename` 仍指向 `softwki`）
- [ ] 给测试加离线 mock：embedding / LLM / LightRAG 不发真实网络请求
- [ ] 修 `tests/test_answer_engine.py` 的陈旧断言（或 skip，并用新契约测试替代）
- 验收：`pytest tests -q` 在无网络环境 60 秒内完成，0 error。

### T1 — PDF 页码与段落

- `softwiki/ingestion/pdf_loader.py`：返回值增加 `pages: [{page_no, text}]`，保留 `cleaned_text` 兼容；
- 空页/扫描页显式记录（`empty_pages`），OCR 可后置，但不能静默变成空文本；
- 验收：3 个 PDF（文本型 / 双栏 / 扫描）能输出每页字符数、空页数。

### T2 — Chunk 元数据与迁移

- `softwiki/source_store/models.py` 的 `Chunk` 增加 `page_start`、`page_end`、`char_start`、`char_end`（nullable）；
- 没有 Alembic：新增 `scripts/migrate_add_chunk_offsets.py`（SQLite `ALTER TABLE`，幂等）；
- 验收：旧库可升级；新库 `create_all` 直接带字段。

### T3 — 统一 chunk 创建

- 现在有 5 处重复：
  - `softwiki/api/server.py:323`
  - `softwiki/cli/main.py:259`
  - `softwiki/mcp/server.py:165` 与 `:218`
  - `softwiki/mcp/sse.py:185`
- 抽成统一入口（`DocumentRepository.create_chunks_from_text` 或 `ingestion/chunker` 的单一函数）；
- 验收：5 处调用同一函数；以后加字段只改一处。

### T4 — RAG 引用带页码/span

- `softwiki/rag/citations.py` 增加 `page` / `span` 字段，`answer_engine.py` 传入；
- `/api/ask` 返回的 sources 增加 `page_start` / `page_end`；
- 验收：引用可显示 “p.12” 并能高亮原文。

### T5 — 全层引用

- `answer_engine.py` 中 claims / graph / timeline / wiki 的上下文行都带 `document_id` + `page/span`；
- `CitationManager` 支持 `doc | claim | event | relation` 四种类型；
- 验收：问时间型/关系型问题，引用里包含 timeline/claim 来源。

### T6 — 弃权与 ask-time scope

- `AnswerEngine.ask` 在检索前调用 `check_scope`；
- 答案后检查：每个结论是否有证据；不足则输出“证据不足 + 缺什么”，不编；
- 验收：库外问题拒答；无证据问题弃权。

### T7 — 认证

- 本地账号表（`users`: id / username / password_hash / role / created_at）；
- 登录 → 会话（cookie 或 JWT）；API/MCP 拒绝匿名；
- 验收：未登录访问 `/api/*` 返回 401；登录后可访问。

### T8 — 按用户 workspace

- 去掉全局 `os.environ["WORKSPACE_DIR"]` 切换，改用 `contextvars` 或显式参数；
- `/api/workspace` 只切换当前会话；MCP `workspace_set` 同理；
- 验收：两个并发会话使用不同 workspace，互不影响。

### T9 — 库级 ACL

- `workspace_members(workspace_id, user_id, role)`，角色：owner / editor / viewer；
- 验收：viewer 不能执行 ingest / index / wiki_build。

---

## 4. P1 任务（试用完整）

### T10 — 模板系统

- `softwiki/templates/analysis/*.yaml`：加载、校验、版本化；
- 内置 `research-report`、`course-qa` 两个模板；workspace 可覆盖；
- 验收：新增学科只加模板，不改引擎代码。

### T11 — 报告异步 + manifest

- 任务表 + 后台 worker（先用进程内队列，不上 Celery）；
- 产物：`exports/reports/<id>/report.md` + `manifest.json`；
- manifest：模板版本、模型、证据 ID、检查结果、耗时、成本；
- 验收：报告可下载；同输入重跑证据集一致。

### T12 — Docker + TLS

- `Dockerfile`、`docker-compose.yml`（app + postgres + caddy/nginx TLS）；
- `/health` 健康检查；
- 验收：干净机器一条命令启动。
- 注：多用户写入建议 Postgres；SQLite 只适合单用户演示。

### T13 — 备份 / 恢复

- `scripts/backup.sh`（DB + workspace）、`scripts/restore.sh`；
- 验收：验收脚本第 10 步。

### T14 — 验收测试与文档

- 每个模板 10 个 golden questions，放 `tests/acceptance/`；
- 安装、运维、验收文档；
- 验收：新机器按文档 30 分钟内跑通。

---

## 5. 里程碑

- **M0 基线**：T0
- **M1 能信**：T1–T6（PDF 页码、全层引用、弃权、scope）
- **M2 能隔离**：T7–T9（认证、按用户 workspace、ACL）
- **M3 能交付**：T10–T14（模板、报告、Docker、备份、验收）

试用版 = M0 + M1 + M2 + M3 的最小集。

---

## 6. 开放问题（需要确认）

1. **20 篇真实 PDF**：学校提供，还是先用现有材料跑基线？
2. **出站 LLM/embedding 是否允许？** 不允许则需要校内模型（vLLM/Ollama），Docker 体积和配置都会变。
3. **数据库**：试用版用 Postgres 还是 SQLite？（建议 Postgres）
4. **扫描版 PDF 是否必须 OCR？** 决定 T1 的范围。

---

## 7. 明确不做

多租户、SSO、集群/高可用、10 个学科、通用工作流 DSL、wiki 自动回写、移动端、完整 RBAC 矩阵。
