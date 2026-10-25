# progress.md — softwiki 进度台账 ★

> **从此刻起，所有推进基于本文件。随时更新。** 下个 session 只读 `AGENTS.md` + 本文件 + `docs/README.md` 即可接手。
> 图例：`[x]` 完成 ｜ `[ ]` 待办 ｜ `[~]` 进行中 ｜ `[!]` 阻塞

## 当前状态（快照）

- **项目**：softwiki = 多策略研究智能引擎（RAG / GraphRAG / LLM-Wiki / ClaimDB / Timeline）。
- **当前阶段**：**试用就绪（Trial Readiness）**，目标 = 单校、单实例、自部署、试用评估。
- **Agent Web（2026-10-24）**：L1/L2 已上线。WebUI **Quick / Agent** 双模式；opencode `1.18.35` 宿主 `:6111`；API `:6200/api/agent/*`；systemd `softwiki-agent-web`；模型 `gpt-4.1-mini`；acceptance **11/11**；浏览器 Agent 模式已验证。
- **范围**：见 `docs/05-roadmap/trial-readiness.md`；2 个深模板（研究报告 / 课程问答），wiki 试用阶段只读。
- **远程**：`ssh://git@10.3.9.19:2222/faye/softwiki.git`（branch `master`）。
- **本 session 已完成**：
  - 修正 venv editable 指向（原指向 `/home/faye/mydrv/git/softwki` 空壳）；
  - 补 `softwiki_search` / `softwiki_ask` 兼容别名，`test_mcp` 恢复可收集；
  - 落地 `docs/05-roadmap/trial-readiness.md`（10 步验收 + P0/P1 任务）；
  - 落地工作方式：`AGENTS.md`、`progress.md`、`opencode.json`、`docs/README.md` 交接段；
  - **commit/push 策略 A 已确认**：逻辑单元自动 commit + 里程碑 / session 结束自动 push；
  - 修复 `softwiki/config.py` 缺少 `typing.Optional` 导入（javis 的 Python 3.13 会直接 NameError）；
  - 核查 javis 部署现状（systemd 三服务 + `make deploy`）；
  - 落地 Docker Compose 栈（API / MCP / Web）+ CI 轮询脚本 + systemd timer；
  - 本地端到端验证通过：API 健康、Web 200、Web `/api` 反代、MCP 端口；
  - 修复 embedding：OpenAI `text-embedding-3-small`（1536 维）+ 分批；重建索引 4196 chunks；
  - 切流完成：Docker 接管 6200/6100/6108，旧 systemd 已 stop + disable；CI timer 已安装并验证；
  - 新建 `armkb`：3 篇 ARM 试点 → 454 chunks / 101 claims / 39 entities / 17 events；`search` + `ask` 验证通过；
  - 全量 81 篇 ARM PDF 后台入库中（日志 `/tmp/armkb-ingest.log`），完成后需 `/api/index`。
- **本 session 提交 / 推送（策略 A）**：
  - `eb6f98d` docs(agents): 项目宪法与进度台账
  - `ae067eb` docs(roadmap): 试用就绪清单
  - `e853318` docs(roadmap): SI-1
  - `7645e5e` fix(mcp): 兼容别名
  - `a3d1c9d` feat(mcp): 双传输
  - `fd69c5b` docs(progress): session 交接
  - `6bdb598` fix(config): Optional 导入
  - `1f9497a` fix(deps): mcp/python-multipart
  - `b0ac803` feat(web): API_INTERNAL_URL
  - `563d992` feat(deploy): Docker Compose
  - `54ba06a` feat(ci): 轮询部署 + timer
  - `ae6357e` docs(progress): 并行栈部署
  - `2bdbbec` feat(embed): 分批 + 独立凭据
  - `62726c3` fix(chunker): 限制 chunk 大小
  - `394e858` chore(deploy): 生产端口
  - `c22c56a` fix(workspace): 工作区根目录
  - `3e2a73e` chore(deploy): 默认 armkb
  - `cde5069` feat(scripts): 批量 PDF 入库
  - 已推送 `origin/master`（`f19c296..cde5069`）。
- **部署现状（javis = 10.3.9.29）**：
  - 机器：x86_64 / Debian 13 / Docker 26.1.5 + Compose 2.26.1 / 62GB RAM / RTX 3090 24GB / 422GB 可用。
  - **当前**：Docker Compose 接管 `6200`（API）/ `6100`（MCP）/ `6108`（Web）；旧 systemd 已 stop + disable；CI timer 每 3 分钟轮询；**Agent Web** 由宿主 systemd `softwiki-agent-web` 接管 `6111`（L1，调用系统 opencode）。
  - **活动库**：`armkb`（API + MCP 启动即 armkb）；`lsl-kb` 仍可通过 API 切换。
- **Demo 范围（2026-10-23 确认）**：权限/用户系统（登录、RBAC、ACL 强制、审计）**不在当期目标**；当前实例按 `wiki-admin` 使用，4 种身份仅作概念/文档保留。
  - **数据库**：PostgreSQL `softwiki_armkb`；SQLite 数据已迁移；vector/BM25 文件仍在 workspace。
  - **ARM 语料**：`~/drvroot/drv_f29/icwork/arm/docs` → javis `/opt/aitools/apps/softwiki/inbox/arm`（81 PDF / 208MB / 约 1.6 万页）。
  - 全量：73 篇文档 / 2122 claims / 835 entities / 1328 relationships / 375 events；81 个 PDF 中 70 success、11 duplicate、0 failed。
  - 数据：`workspace/` bind mount；embedding 用 OpenAI 1536 维；`armkb` 39,870 chunks，全量索引已完成。
  - 抽取：`cheap_extraction` / `wiki_compilation` 已切 DeepSeek（Google 402）；抽取窗口仍是每篇前 15k 字符。
  - 旧 clone `~/mydrv/git/softwiki` 的 `84e25ae`（Makefile CI/CD）未推送，但已被 Docker CI 取代。
  - Ollama 仍可用（`nomic-embed-text` 等），但当前不用于 embedding。

## 研发计划（checklist）

### M0 — 基线（试用前置）
- [x] 修正 venv editable 指向本仓库
- [x] 补 `softwiki_search` / `softwiki_ask` 别名
- [x] 清理 `tests/__pycache__`
- [x] 测试离线化（mock embedding / 禁用 LightRAG / Web）
- [x] 修 `test_answer_engine` / `test_config_cascade` / `test_workspace` 陈旧断言
- [x] `pytest tests -q`：**54 passed，约 2s**

### M1 — 能信（P0）
- [x] T1 PDF 页码/段落（`--- Page Break ---` → page ranges）
- [x] T2 Chunk 元数据 + 幂等迁移
- [x] T3 统一 chunk 创建（`DocumentRepository.build_chunk_models`）
- [x] T4 RAG 引用带页码/span
- [x] T5 全层引用（claim / graph / timeline）
- [x] T6 弃权 + ask-time scope
- [x] T15 抽取窗口化（`EXTRACTION_MAX_WINDOWS=6` spread）+ hash claim id + 关系/事件去重；`softwiki reextract` 已完成 73/73

### M2 — 能隔离（P0）
- [~] T7–T9 认证/ACL：代码在，但 **demo 阶段不启用**；不接 WebUI 登录、不做权限强制
- 注：当前实例按 `wiki-admin` 使用；`SOFTWIKI_AUTH_ENABLED` 保持关闭

### M3 — 能交付（P1）
- [x] T10 模板系统（`research-report` / `course-qa`）
- [~] T11 报告 + manifest（同步版已通；异步任务未做）
- [x] T12 Docker Compose + CI/CD（TLS/反代未做）
- [x] T13 备份 / 恢复脚本（workspace + `pg_dump` 文档）
- [x] T16 PostgreSQL（`DATABASE_URL_TEMPLATE` + compose postgres + SQLite→PG 迁移；armkb 已迁移 73 docs / 39,870 chunks）
- [x] T17 基础 workflow 选择（API/MCP/CLI/report，prompt 注入 `academic-analysis`）
- [x] T21 `/api/ask` 接 `mode`/`history`；sources 与答案引用编号对齐
- [x] T22 WebUI：workflow 选择、页码展示、Report 下载
- [x] T23 Golden questions + `scripts/run_acceptance.py`（11/11 passed）
- [ ] T18 Workflow 高级：自动路由、BM25/timeline verifier、可视化编辑

### M4 — Agent Web（opencode）
> 计划：`docs/05-roadmap/agent-web-plan.md`
- [x] L1：`prepare_agent_runtime()` + `softwiki agent-web` + WebUI Agent 入口
- [x] Agent 允许 `softwiki_search` / `softwiki_retrieve`，并要求页码引用/弃权
- [x] 设置 `SHELL_MODEL=gpt-4.1-mini` / `SHELL_API_BASE` / `SHELL_API_KEY`
- [x] L2：`/api/agent/*` 代理 + Quick/Agent 切换 + research steps（非流式）
- [x] L1/L2 部署与 KB 验证（armkb reindex 完成；acceptance 11/11；浏览器 Agent 模式已验证）
- [x] 修复 `AnswerEngine` 把 "List/Summary" 研究问题误判为 inventory
- [ ] L2 流式输出（SSE / 逐 token）
- [ ] 独立 `softwiki-agent` 容器，pin opencode `1.18.35` + 升级冒烟测试

## Pending issues / Blocker

- [x] **真实 PDF**：已提供 81 篇 ARM 技术文档。
- [~] **出站 LLM/embedding**：当前用 OpenAI + DeepSeek；学校内网是否允许出站仍未确认。
- [x] **测试基线**：54 passed（离线）。
- [x] **数据库**：PostgreSQL 已切换并迁移（SQLite 作为回退）。
- [ ] **OCR 范围**：扫描版 PDF 未支持。
- [x] javis deploy key 已加入 Forgejo。
- [x] **embedding 已修复**：OpenAI `text-embedding-3-small`（1536 维），分批 + 并发 + TPM 限速。
- [x] **切流**：Docker 接管 `6200/6100/6108`，旧 systemd 已 disable。
- [x] **CI timer 已重新启用**。
- [x] **armkb 全量索引完成**：`{"status":"success","indexed_chunks":39870}`；`search`（页码）、`ask`（页码引用）、`/api/report` 均已验证。
- [x] **armkb 数据**：73 篇 / 39,870 chunks / 10,573 claims / 4,165 entities / 7,211 relationships / 639 events。
- [x] **armkb 窗口化重抽完成**：73/73；最终 10,573 claims / 4,165 entities / 7,211 relationships / 639 events；acceptance **11/11**。
- [!] **Workflow 目前只是 prompt 注入**：没有自动路由/verifier 执行；`workflows.yaml` 的 `modes` 字段仍未使用。
- [!] **TUI 不是沙盒**：调用系统 opencode，配置/会话隔离，但文件系统/网络是用户权限；打包/升级见 `docs/05-roadmap/agent-web-plan.md`。
- [!] **TUI 默认不读 KB**：`agent_soul.md` 禁止 `softwiki_search/ask/retrieve`；Agent Web 已新增 `wiki-research` 并开放只读 KB 工具。
- [x] **armkb reindex 完成**：2026-10-24 agent 误调 `softwiki_rebuild_index` 后重跑全量索引；39,870 chunks，`softwiki_search` / `softwiki_ask` / acceptance 11/11 已验证。已用 opencode permission 禁止写工具。
- [ ] **Agent source 标题**：部分 PDF 抽取标题为 `Untitled Document`；页码有效，标题清洗待做。
- [ ] **Agent SSE**：L2 目前是轮询非流式；逐 token/工具事件输出待做。
- [x] **Agent 长请求**：Next rewrite 默认 30s 超时导致 33s 的 agent 回答被前端误报 `Invalid response`；已设 `experimental.proxyTimeout=300_000`，并修正错误文案。
- [x] **Agent source 元数据**：从答案引用解析出的 source 之前 `Unknown / 0%`；现用 KB 反查 `source_name`/日期/页码/摘录，无检索分数的 source 隐藏百分比。
- [x] **Agent 链接**：`/agent` 同源 307 → 当前 host:6111，不再写死 localhost。
- [ ] **Agent Session / 沙盒 / 审核**：设计见 `docs/05-roadmap/agent-session-sandbox-plan.md`；P0/P1 待确认后开工。
- [!] **remote MCP 仍暴露写工具**：当前靠 opencode permission 拦截；产品化需只读 MCP sidecar / 网关。
- [ ] **Postgres 备份**：文档已写 `pg_dump`，尚未纳入 `scripts/backup.sh`。
- [!] **密钥明文**：`model_profiles.yaml` 仍有明文 DeepSeek key；OpenAI key 曾在聊天暴露，建议轮换。
- [ ] **TLS/反代**：javis 无 Caddy/Nginx；试用先用 HTTP。
- [x] **认证/权限**：demo 阶段明确不做（代码保留，默认关闭）。

## 下一步（NEXT）

1. **Demo**：按 `docs/04-guides/demo.md` 跑 Quick + Agent；acceptance 11/11；继续补 golden questions。
2. **Agent L2 产品化**：SSE 流式、工具事件、独立 `softwiki-agent` 容器（pin `1.18.35`）。
3. **数据质量**：清洗 `Untitled Document` 标题；补 PDF 元数据。
4. **lsl-kb**：历史 820 篇 claims/events 仍为 0，决定重抽或迁移。
5. **Workflow 高级**：自动路由、BM25/timeline verifier、可视化编辑。

## 本 session 状态记录（handoff）

- **做了什么**：确认工作方式（AGENTS.md / progress.md / docs-first / 小步提交）；确认试用边界（单校自部署、答案+报告、手动/自动/关闭三态裁决）；定位并修复 venv 与 MCP 别名问题；落地试用清单；核查 javis 现有 systemd 部署；落地 Docker Compose + CI 轮询并本地端到端验证；完成 javis 切流；修复 OpenAI embedding 与 chunk 上限，重建索引并验证 `search`/`ask`；新建 `armkb` 并启动 81 篇 ARM 技术文档入库。
- **关键产物**：
  - `AGENTS.md`（项目宪法）
  - `progress.md`（本文件）
  - `docs/05-roadmap/trial-readiness.md`（10 步验收 + P0/P1 任务）
  - `Dockerfile` / `docker-compose.yml` / `scripts/ci-deploy.sh` / `docs/03-operations/deployment-javis.md`
  - `docs/06-archive/session-report-2026-10-23.md`（本轮完整报告）
- **易踩坑**：
  - `venv` 的 editable 安装原本指向 `/home/faye/mydrv/git/softwki`（空壳），导致测试导入错仓库；
  - `tests/__pycache__` 里的旧 `.pyc` 仍带旧路径；
  - 全量 pytest 会挂起，必须先离线 mock；
  - `mcp>=2` 会把 `FastMCP` 改名并破坏 `softwiki.mcp.sse`，必须 `<2.0.0`；
  - OpenAI embedding 单条上限 8192 tokens；旧 `chunk_text` 在无标点长段落上产出过 56k 字符 chunk，必须在 chunker 层限长；
  - OpenAI 账户 TPM 只有 1M；40M 字符语料至少要 45–60 分钟，batch=500+4 并发会 429；必须用 `EMBEDDING_TPM` 限速器；
  - `/api/index` 重建 chunk 会换 ID；向量索引必须先 `reset()`，否则索引指向已删除的 chunk，搜索返回空；
  - `/api/ingest/file` 只建 Document + 后台抽取，不切块/不向量化；必须再调 `/api/index`；
  - `run_extraction_pipeline` 只取前 15k 字符，大手册结构化层不完整；
  - `switch_workspace` 是进程级；容器重启后以 `SOFTWIKI_ACTIVE_WORKSPACE` 为准（已设 armkb）；
  - Next.js 在 Docker 内反代要 `API_INTERNAL_URL=http://api:6200`，不能用 `127.0.0.1`；
  - `docker compose config` 会把 `.env` 里的真实密钥渲染出来，不要贴日志；
  - `/api/ask` 会重复检索一次，且 `AskRequest` 丢弃 `mode`/`history`；
  - `scope guard` 没有接进 `AnswerEngine.ask`；
  - workspace 切换是全局 `os.environ`，并发用户会互相覆盖。
- **2026-10-24 Agent Web 追加**：
  - L1：`softwiki agent-web`（默认 `:6111`，`wiki-research`，remote MCP `:6100/mcp`）；宿主 systemd `softwiki-agent-web`；WebUI Sidebar **Agent** + ChatPanel **Agent ↗**。
  - L2：`GET /api/agent/status`、`POST /api/agent/ask`（轮询 opencode session）、`POST /api/agent/session`、abort/delete；ChatPanel **Quick / Agent** 切换 + research steps + answer reference parser。
  - Agent 安全：opencode permission deny `bash`/`edit`/`softwiki_ingest`/`index`/`rebuild_index`/`wiki_build`/`modules_set`/`workspace_set`；`steps=20`。
  - 关键配置：`SHELL_MODEL=gpt-4.1-mini`（`gpt-5-mini` 不接受 `max_tokens`）；`AGENT_WEB_URL=http://host.docker.internal:6111`；`deploy/softwiki-agent-web.service`。
  - 验证：`/api/agent/status` available；浏览器 Agent 模式 2 个工具（`softwiki_ask` + `softwiki_search`）出答案/页码/1 source；acceptance 11/11。
  - 2026-10-24 追加：`/agent` 同源重定向；Next `proxyTimeout=300_000` 修复 30s 超时误报；长问题 CM55+NIC400+U55 浏览器实测 50s 出答案 + 2 steps + 3 sources。source 卡片现从 KB 反查 source_name/日期/页码/摘录；无检索分数时不再显示 0%。
  - 事故：首次验收 agent 误调 `softwiki_rebuild_index`，全量 reindex 约 45 分钟；已 abort/restart + reindex，且 permission deny 写工具。MCP/向量缓存需重启容器清空。
  - 已知限制：remote MCP 仍暴露写工具（靠 opencode permission）；L2 非流式；PDF 标题 `Untitled Document`；宿主 opencode 未 pin。
- **可回收**：所有结论已落库。下个 session 读 `AGENTS.md` + `progress.md` + `docs/05-roadmap/agent-web-plan.md` + `docs/04-guides/demo.md` 即可接手。
