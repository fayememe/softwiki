# Session Report — 2026-10-23

> 范围：试用就绪（Trial Readiness）第一轮落地。
> 目标：单校、单实例、自部署、试用评估。
> 结论：**核心链路已通，测试全绿；armkb 已完成全量索引、PostgreSQL 迁移和窗口化重抽（10,573 claims）；workflow/API/UI demo 链路已打通；acceptance 11/11。**

---

## 1. 本 session 完成了什么

### 1.1 工作方式

- 新增 `AGENTS.md`：会话一次性、文档持久、docs-first、chat/git/progress 规范。
- 新增 `progress.md`：当前状态 / checklist / pending / NEXT / 交接。
- 新增 `opencode.json`：自动加载 `AGENTS.md` + `progress.md` + `docs/README.md`。
- `docs/README.md` 增加「当前状态 / 交接」。

### 1.2 部署与 CI

- Docker Compose 栈：`api` / `mcp` / `web`，多阶段 Dockerfile。
- javis 接管 `6200`（API）/ `6100`（MCP）/ `6108`（Web），旧 systemd 已 stop + disable。
- CI：javis 上 3 分钟轮询 `origin/master`，flock + SHA 比对 + 构建 + 健康检查 + 回滚。
- `deploy/softwiki-deploy.timer` 已安装并验证；**入库/索引期间临时停止**。
- 修复 `mcp>=2` 破坏 `FastMCP` 的问题，pin `mcp<2`。
- 修复 Docker 内 Next.js 反代：`API_INTERNAL_URL=http://api:6200`。
- 修复多 workspace 解析：`WORKSPACES_ROOT` / `WORKSPACE_DIR` 父目录。
- 修复 `config.py` 缺少 `typing.Optional`（Python 3.13 NameError）。

### 1.3 回答正确性（T1–T6）

- `Chunk` 增加 `page_start/page_end/char_start/char_end`，带幂等迁移。
- PDF 的 `--- Page Break ---` 映射到页码；chunk 头带 `Page/Pages`。
- `chunk_text` 强制最大长度，修复无标点长段落产生 56k 字符 chunk 的问题（OpenAI 8192 token 限制）。
- `CitationManager` 支持按 `(doc, page)` 去重，引用显示 `p.N` / `pp.N-M`。
- claims / relationships / events 全部附加文档引用（T5）。
- `AnswerEngine.ask` 检索前执行 scope；库外问题直接拒绝。
- 空库/无证据时显式弃权，不再调用 LLM 编答案。
- wiki 编译遇到 LLM 失败时回退到模板页，不再整体失败。
- 测试基线：全量离线，**48 passed**。

### 1.4 认证 / 报告 / 运维

- 认证（**默认关闭**）：
  - PBKDF2 密码哈希、HMAC 签名 token、`users` / `workspace_members`。
  - `/api/login`、`/api/logout`、`/api/me`、`/api/health`。
  - 按请求 workspace contextvar + 库级 ACL。
  - `scripts/create_admin.py`。
- 报告：
  - `research-report` / `course-qa` 模板。
  - `POST /api/report` → `exports/reports/<id>/report.md` + `manifest.json`。
- 备份/恢复：`scripts/backup.sh` / `scripts/restore.sh`。
- Embedding：
  - OpenAI `text-embedding-3-small`（1536 维），分批 + 并发 + 429 重试。
  - 独立 `EMBEDDING_API_KEY/BASE`，不污染 chat 的 Google/DeepSeek 配置。
  - `EMBEDDING_TPM` 限速器，避免撞 1M TPM。
- 抽取：`cheap_extraction` / `wiki_compilation` 从 Google（402）切到 DeepSeek。
- 抽取窗口：每篇按 `EXTRACTION_MAX_WINDOWS` 采样窗口（默认 6）；claim id 改 hash，关系/事件去重；`softwiki reextract` 回填。
- PostgreSQL：`DATABASE_URL_TEMPLATE` + compose `postgres:16` + SQLite→PG 迁移；armkb 已迁移（73 docs / 39,870 chunks）。
- Workflow：模板 + workspace override；`academic-analysis`；API/MCP/CLI/report 可按请求选择，注入 answer prompt。

### 1.5 ARM 知识库 armkb

- 语料：`~/drvroot/drv_f29/icwork/arm/docs` → javis `inbox/arm`。
- 81 个 PDF：70 success / 11 duplicate / 0 failed。
- 73 篇文档。
- 抽取：**2122 claims / 835 entities / 1328 relationships / 375 events**。
- 39,870 chunks / 约 40M 字符。
- 试点 3 篇已验证 `search` + `ask`（PL031 寄存器表、Ethos-U55）。

---

## 2. 关键根因记录

| 问题 | 根因 | 处理 |
|---|---|---|
| 测试挂起 | `test_workspace` 进入 fallback REPL 等输入 | patch `shutil.which` |
| 测试联网/402 | LightRAG + Google 在测试中初始化 | `SOFTWIKI_DISABLE_LIGHTRAG` / mock embeddings |
| wiki build 失败 | Google 402 直接抛出 | 捕获并回退模板页 |
| chunk 超限 | 无标点长段落未切分，单 chunk 56k 字符 | chunker 强制限长 |
| Docker workspace 切换失效 | 用包路径而不是 `WORKSPACE_DIR` 父目录 | `get_workspaces_root()` |
| 索引极慢/429 | 39,870 chunks、账户 1M TPM；batch 500+4 并发超限 | batch 100 + 并发 2 + TPM 限速器 + 5 次退避 |
| 索引与 chunk ID 不一致 | 第二次 index 重建了 chunk，但向量缓存未清 | `LocalVectorStore.reset()` |
| 搜索结果为空 | 缓存/旧索引指向已删除 chunk | 同上 + 完整重建 |
| MCP 2.x 崩溃 | FastMCP 改名 | pin `mcp<2.0.0` |

---

## 3. 测试

```bash
./venv/bin/python -m pytest tests -q
# 48 passed in ~1.7s
```

新增/修复的测试：

- `tests/test_chunker.py`：长 ASCII / CJK / 多句限长。
- `tests/test_chunker_pages.py`：页码映射。
- `tests/test_citations.py`：页码格式与去重。
- `tests/test_abstain.py`：空库弃权。
- `tests/test_workspace_root.py`：workspace 根目录解析。
- `tests/test_auth.py`：密码哈希、token 签名/过期/篡改。
- `tests/test_report.py`：模板加载、报告与 manifest。
- `tests/conftest.py`：离线 mock embedding、禁用 LightRAG/Web 搜索。

---

## 4. 当前部署状态

| 项 | 值 |
|---|---|
| 主机 | javis `10.3.9.29`（x86_64 / Debian 13 / 62GB RAM / RTX 3090 / 422GB 可用） |
| Web | `http://10.3.9.29:6108` |
| API | `http://10.3.9.29:6200` |
| MCP | `10.3.9.29:6100`（SSE + Streamable HTTP） |
| 活动库 | `armkb` |
| 容器 | `softwiki-api-1` / `softwiki-mcp-1` / `softwiki-web-1`，全部 healthy |
| CI timer | **active** |
| 最新 commit | 见 `git log -1` |

`.env` 关键项（不记录值）：

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=100
EMBEDDING_CONCURRENCY=2
EMBEDDING_TPM=900000
SOFTWIKI_ACTIVE_WORKSPACE=armkb
```

---

### 4.1 验收证据

- `search "PL031 registers"` → PL031 TRM `page_start=5, page_end=7`。
- `ask "What registers does the PL031 RTC provide?"` → 引用包含 `p.12`、`pp.9-10`、`p.23` 等页码。
- `/api/report` → `20261023-204514-b20cb2063f91`，`report.md` + `manifest.json` 可下载。
- `pytest tests -q` → 48 passed。

## 5. 未完成 / 风险

- [x] **armkb 全量索引已完成**：39,870 chunks；2026-10-23 12:50–13:38（约 48 分钟，1M TPM）。
- [x] **已验证**：`search` 返回 page_start/page_end；`ask` 引用显示 `p.N` / `pp.N-M`；`/api/report` 生成并下载 report.md + manifest.json。
- [x] **抽取窗口**：已改为窗口采样（本次 4 窗口/篇）+ hash claim id + 去重；73/73 重抽完成。
- [ ] **认证 UI**：后端已就绪，WebUI 没有登录页；线上 auth 默认关闭。
- [ ] **TLS/反代**：javis 没有 Caddy/Nginx；试用先用 HTTP 端口。
- [x] **数据库**：已切 PostgreSQL；SQLite 数据已迁移。
- [!] **密钥**：OpenAI key 曾出现在聊天；建议轮换。`model_profiles.yaml` 仍有明文 DeepSeek key，建议移到 `.env` / secret store。
- [ ] **lsl-kb**：历史 820 篇 claims/events 仍为 0（未重抽）。

---

## 6. 接手步骤

1. 索引已完成（`{"status":"success","indexed_chunks":39870}`）。
2. 验证：
   ```bash
   curl -fsS http://127.0.0.1:6200/api/status
   curl -X POST http://127.0.0.1:6200/api/report \
     -H 'Content-Type: application/json' \
     -d '{"question":"What registers does the PL031 RTC provide?","template":"research-report"}'
   ```
3. CI timer 已重新启用；acceptance：`python scripts/run_acceptance.py --api http://10.3.9.29:6200` → 11/11。
4. 后续优先级：
   - Workflow 高级（verifier/自动路由）；
   - 增量索引；
   - lsl-kb 重抽；
   - 权限/登录（demo 后再做）。

---

## 7. 本 session 关键提交

```
e42ef5a feat(workflows): per-request workflow selection
9889b1a fix(api): redact credentials in status response
db200e5 fix(db): skip text primary keys when resetting Postgres sequences
370844d feat(db): support PostgreSQL per workspace
8ec4d7f feat(extraction): window documents instead of first 15k chars
```

早期提交：

```
274b21d fix(index): reset vector cache before rebuilding
0a861d2 fix(embed): pace OpenAI requests under the TPM limit
d81e2a5 perf(index): use ndarray vector store and cached BM25
71ac6ba chore(ci): allow longer startup warmup
68f83f1 chore(ops): add workspace backup and restore scripts
a27df29 feat(report): analysis templates and markdown report artifacts
34ee268 feat(auth): local users, signed tokens, and workspace ACL
34a2e20 test: cover page mapping, citations, and abstain
f94be45 feat(citations): page-level and all-layer citations
1cb3975 feat(chunk): add page and character offsets
74f4a93 test: make suite offline and update stale assertions
ca92ee6 fix(wiki): fall back to template when LLM compilation fails
c8bcb4e fix(answer): enforce scope before retrieval
```

---

## 8. 主线 TODO 审计（2026-10-23）

### 已完成

- M0 测试基线：53 passed。
- M1 回答可信：页码/偏移、页码引用、全层引用、弃权、scope。
- M2 隔离基础：认证/ACL 代码（默认关闭）。
- M3 交付基础：Docker/CI、模板、报告、备份、Postgres。
- 抽取窗口化 + hash claim id + 关系/事件去重 + 并行抽取器。
- 基础 workflow 选择：模板 + workspace override + `academic-analysis`；API/MCP/CLI/report 可按请求选择。

### 仍未做（按优先级）

**P0（试用前应完成）**

1. [x] 窗口化重抽完成：73/73，10,573 claims。
2. [x] Golden questions：11/11 passed。
3. [x] API `mode`/`history` 与 sources 引用一致性已修复。
4. [x] WebUI workflow/页码/Report 已接入。
5. [ ] Postgres 备份脚本：文档已写 `pg_dump`，`scripts/backup.sh` 尚未包含。
6. [ ] 权限/登录：demo 阶段明确不做。

**P1（产品深度）**

1. **Workflow 高级**：当前只是 prompt 注入；缺自动路由、BM25 事实校验、timeline 时序校验、失败降级策略、可视化/受约束的模板编辑。
2. **SI-1 Wiki 提示词系统**：`page_generator.py` 仍硬编码 system prompt + 固定章节；未支持 workspace/topic 覆盖。
3. **增量索引**：`/api/index` 仍全量重切/重嵌；1M TPM 下每次约 50 分钟，应做缺失 chunk 的增量索引。
4. **抽取覆盖/质量**：窗口是采样（默认 6 → 本次 4），不是全文档；需要评估哪些文档/章节值得全量抽取。
5. **lsl-kb 回填**：历史 820 篇 claims/events 仍为 0；决定重抽或迁移到 armkb 流程。
6. **审计日志**：auth/ACL 有角色，但没有操作审计。

**P2（路线图后续）**

1. Phase 2 图像系统：上传、服务、图表 OCR、图搜。
2. Phase 3 远程 MCP HTTPS + Bearer、swshell 独立客户端。
3. Phase 5 Wiki 手工编辑 / 混合模式 / 页面编辑器 / 独立站 / 静态导出。
4. Phase 6 响应式、web_loader 升级、测试覆盖扩展。
5. TLS/反代：按你的要求暂不做。


---

## 9. Demo 范围决策（2026-10-23）

- 现阶段以 **demo** 为主；**权限 / 用户系统不作为当期目标**。
- 不做：登录页、users 表使用、RBAC 强制、ACL 强制、审计日志。
- 4 种身份（`wiki-admin` / `wiki-manage` / `wiki-work` / `wiki-study`）继续作为文档/模式概念保留；当前实例按 `wiki-admin` 使用。
- 认证代码保留在仓库，但 `SOFTWIKI_AUTH_ENABLED` 保持关闭，不参与 demo 流程。
