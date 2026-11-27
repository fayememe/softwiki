# progress.md — softwiki 进度台账 ★

> **从此刻起，所有推进基于本文件。随时更新。** 下个 session 只读 `AGENTS.md` + 本文件 + `docs/README.md` 即可接手。
> 图例：`[x]` 完成 ｜ `[ ]` 待办 ｜ `[~]` 进行中 ｜ `[!]` 阻塞

## 当前状态（快照）

- **项目**：softwiki = 多策略研究智能引擎（RAG / GraphRAG / LLM-Wiki / ClaimDB / Timeline）。
- **当前阶段**：**试用就绪（Trial Readiness）**，目标 = 单校、单实例、自部署、试用评估。
- **SWAgent（2026-10-24）**：L1/L2 已上线。WebUI **Quick / SWAgent** 双模式；opencode engine pin **1.19.5**（内置路径 `/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode`）宿主 `:6111`；API `:6200/api/agent/*`；systemd `softwiki-agent-web`；模型 `gpt-4.1-mini`；acceptance **11/11**；浏览器 Agent 模式已验证。
- **知识系统思想（2026-10-25）**：已落 `docs/02-design/knowledge-system-philosophy.md`（Claim 为事实源；Graph/Timeline/Wiki 为投影；重复/冲突/版本/人工裁定；LLM-Wiki 方法论与规模策略）。实现计划/难度：`docs/05-roadmap/knowledge-system-plan.md`。
- **Knowledge v2 v0（2026-10-30）**：schema v2 + canonical claim 9,766 / evidence 10,573；Conflicts API/UI；Adjudication API/UI；AnswerEngine 只读 active/disputed；12 个 Wiki 页面已用 canonical claims 重建，stale 0；Graph 6,994/7,211、Timeline 599/639 已挂 canonical claim；Wiki rebuild worker + artifact history；structured claim fields + NLI judge（1 个真实冲突，2 claims disputed）；近重复候选 6 对；备份 `/tmp/kb_alpha_before_knowledge_v2.sql`（116MB）。
- **Wiki Prompt Studio + 三级分类（2026-10-25）**：提示词作为可选 intervention 层；Preview/Apply/保存；左侧改为 **IP 产品 / 协议 / 技术** 三级（IP 子类 CPU/NPU/AMBA/DMA/Other；协议 AMBA/PQ/指令集；技术 System/Low Power/SoC）；合并页 alias-aware；`GET /api/wiki/coverage`。当前 claim 覆盖率 **15.94%**（1,685/10,573；ignored 1,107；effective 17.80%）。**12 个策展页面已生成**；旧 4 页已归档。
- **范围**：见 `docs/05-roadmap/trial-readiness.md`；2 个深模板（研究报告 / 课程问答），wiki 试用阶段只读。
- **Demo/销售（2026-10-31）**：`docs/04-guides/demo-plan.md`（15/30 分钟脚本、失败预案）；`docs/04-guides/sales-training.md`（话术、异议、边界）。
- **角色/权限（2026-10-31）**：`docs/02-design/roles-permissions.md`；4 角色 capability mapping；Web role cookie、MCP `X-SoftWiki-Role`、`configs/permissions.yaml` 可改；team trial `wiki-work` 已开放 ingest/index（Hermes）；document delete canonical cleanup；**MCP role header 实测**（study 拒绝 ingest，work 放行）；无效 base64 已拒绝。
- **远程**：`ssh://git@git.example.internal:2222/operator/softwiki.git`（branch `master`）。
- **trial-host team trial（2026-11-02）**：`trial.example.internal`，两个独立 KB（目标各 **100–200 篇**，按 150 篇/库推进；pilot 20/库）：`coffee-kb`（Web `6108` / MCP `6100` / API `127.0.0.1:6200` / DB `softwiki_coffee`）和 `ai-history-kb`（Web `6109` / MCP `6102` / API `127.0.0.1:6202` / DB `softwiki_ai_history`）；**`team` 已删除，kb-alpha 未部署**；opencode 1.19.5；oneroute/DeepSeek；BM25 fallback；Hermes WebUI `9119` 已配置两个 MCP（`softwiki_coffee` / `softwiki_ai`），16 tools each；详见 `docs/03-operations/deployment-trial.md`。
- **trial-host 语料已达标（2026-11-03）**：`coffee-kb` **185 docs / 3,489 chunks / 6,691 claims / 8,179 rel / 2,297 events**；`ai-history-kb` **160 docs / 5,497 chunks / 9,526 claims / 12,067 rel / 3,279 events**；两库 stale wiki 0，`/api/ask` 引用正常。做法：**开发机抓正文 → markdown + front matter 推送入库**，绕开 trial-host 出口封锁（见 `deployment-trial.md`「出口封锁实测」）。
- **多 KB v0（2026-11-19）**：`docs/02-design/multi-kb.md`；一个 MCP 端口服务全部知识库。`kb_list` / `kb_describe`（零 DB）+ `ask`/`search` 的 `kb` 参数 + 请求级 workspace（ContextVar，不写 `os.environ`）+ `/api/kb`；描述三级回退 `meta.yaml` → `scope.md` → `topics.yaml`；engine 按 DB URL 缓存并限 32；auth 关闭时 `/api/workspace`、`/wiki/switch` 返回 403。**本机 Docker 已验证**（6300/6301/6308）：交替 4 次 + 并发 6 请求均不串库；MCP 调用后默认库未被污染；`/api/kb` 零 DB。**尚未部署到 trial-host。**
- **trial-host 已部署本轮功能（2026-11-19 部署 / 2026-11-20 重启复核）**：身份接入 / 审计 / 建库向导 / 图谱重写已上线两栈；12/12 验收项全过；数据未变（coffee 185 篇 / 6,691 claims，ai 160 篇 / 9,526 claims）。卡死容器已清除，ai 栈交还 compose 管理，API 回到 `127.0.0.1:6202`。详见 `docs/03-operations/deployment-trial.md`「2026-11-19 部署」。
- **本 session 已完成**：
  - 修正 venv editable 指向（原指向 `/home/operator/mydrv/git/softwki` 空壳）；
  - 补 `softwiki_search` / `softwiki_ask` 兼容别名，`test_mcp` 恢复可收集；
  - 落地 `docs/05-roadmap/trial-readiness.md`（10 步验收 + P0/P1 任务）；
  - 落地工作方式：`AGENTS.md`、`progress.md`、`opencode.json`、`docs/README.md` 交接段；
  - **commit/push 策略 A 已确认**：逻辑单元自动 commit + 里程碑 / session 结束自动 push；
  - 修复 `softwiki/config.py` 缺少 `typing.Optional` 导入（build-host 的 Python 3.13 会直接 NameError）；
  - 核查 build-host 部署现状（systemd 三服务 + `make deploy`）；
  - 落地 Docker Compose 栈（API / MCP / Web）+ CI 轮询脚本 + systemd timer；
  - 本地端到端验证通过：API 健康、Web 200、Web `/api` 反代、MCP 端口；
  - 修复 embedding：OpenAI `text-embedding-3-small`（1536 维）+ 分批；重建索引 4196 chunks；
  - 切流完成：Docker 接管 6200/6100/6108，旧 systemd 已 stop + disable；CI timer 已安装并验证；
  - 新建 `kb-alpha`：3 篇 ARM 试点 → 454 chunks / 101 claims / 39 entities / 17 events；`search` + `ask` 验证通过；
  - 全量 81 篇 ARM PDF 后台入库中（日志 `/tmp/kb-alpha-ingest.log`），完成后需 `/api/index`。
- **trial-host 部署注意**：两个独立 KB（coffee / ai-history）；目标机无 CI timer；需手动同步/rebuild；Web/SWA/MCP 公网无 auth，必须安全组限制；当前 embedding 走 oneroute，仍有 BM25 fallback；交付/运维手册见 `docs/03-operations/operator-manual.md`；模型要求见 `docs/03-operations/model-requirements.md`；已支持 `EMBEDDING_DIMENSIONS` 与 `LLM_DISABLE_THINKING`。
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
  - `3e2a73e` chore(deploy): 默认 kb-alpha
  - `cde5069` feat(scripts): 批量 PDF 入库
  - 已推送 `origin/master`（`f19c296..cde5069`）。
- **部署现状（build-host = build.example.internal）**：
  - 机器：x86_64 / Debian 13 / Docker 26.1.5 + Compose 2.26.1 / 62GB RAM / RTX 3090 24GB / 422GB 可用。
  - **当前**：Docker Compose 接管 `6200`（API）/ `6100`（MCP）/ `6108`（Web）；旧 systemd 已 stop + disable；CI timer 每 3 分钟轮询；**Agent Web** 由宿主 systemd `softwiki-agent-web` 接管 `6111`（L1，调用系统 opencode）。
  - **活动库**：`kb-alpha`（API + MCP 启动即 kb-alpha）；`lsl-kb` 仍可通过 API 切换。
- **Demo 范围（2026-10-23 确认）**：权限/用户系统（登录、RBAC、ACL 强制、审计）**不在当期目标**；当前实例按 `wiki-admin` 使用，4 种身份仅作概念/文档保留。
  - **数据库**：PostgreSQL `softwiki_kb_alpha`；SQLite 数据已迁移；vector/BM25 文件仍在 workspace。
  - **ARM 语料**：`~/drvroot/drv_f29/icwork/arm/docs` → build-host `/opt/aitools/apps/softwiki/inbox/arm`（81 PDF / 208MB / 约 1.6 万页）。
  - 全量：73 篇文档 / 2122 claims / 835 entities / 1328 relationships / 375 events；81 个 PDF 中 70 success、11 duplicate、0 failed。
  - 数据：`workspace/` bind mount；embedding 用 OpenAI 1536 维；`kb-alpha` 39,870 chunks，全量索引已完成。
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

### M2.5 — 多 KB（2026-11-19）
> 设计：`docs/02-design/multi-kb.md`
- [x] 请求级 workspace：`softwiki/kb/context.py`（ContextVar，不写 `os.environ`）
- [x] `kb_list` / `kb_describe` MCP 工具（L1 零 DB）
- [x] `ask` / `search` 加 `kb` 参数（stdio + SSE/Streamable HTTP 双传输）
- [x] `POST /api/ask` 加 `kb`；新增 `GET /api/kb`
- [x] `META`/`scope.md`/`topics` 三级描述回退（`softwiki/kb/registry.py`）
- [x] engine 改为按 DB URL 缓存字典 + LRU 上限（`SOFTWIKI_ENGINE_CACHE_MAX`）
- [x] auth 关闭时 `/api/workspace` 与 `/wiki/switch` 返回 403
- [x] `X-SoftWiki-KB` 头选择库（MCP 中间件）
- [x] 测试 `tests/test_multi_kb.py` 16 项；全量 **111 passed**
- [x] 本机 Docker 部署验证（6300/6301/6308 四容器 healthy；跨库/并发/边界全部通过）
- [x] `/api/kb?verify=true` 实例可用性探测（`softwiki/kb/health.py`，TTL 15s / 超时 3s）
- [x] `meta.yaml` 可选 `web_url`；库选择器改为数据驱动（原为写死端口）
- [x] **每栈私有 workspace 根**：`workspace/stacks/<stack>/<kb>`，容器只挂自己的根
      （`SOFTWIKI_STACK_ROOT`），identity / audit 单独共享挂载
- [x] `scripts/kb_layout_migrate.py` 迁移脚本（默认 dry-run，校验 `.softwiki/`）
- [x] trial-host 实测：加库 = 在库根加目录 + `CREATE DATABASE`，即时可见
- [ ] WebUI 的 KB 选择器改为传 `kb`（目前仍是跨端口跳转）
- [ ] 跨库叠加（v1）；`with_stats`；`meta.yaml` 建库模板

### M3 — 能交付（P1）
- [x] T10 模板系统（`research-report` / `course-qa`）
- [~] T11 报告 + manifest（同步版已通；异步任务未做）
- [x] T12 Docker Compose + CI/CD（TLS/反代未做）
- [x] T13 备份 / 恢复脚本（workspace + `pg_dump` 文档）
- [x] T16 PostgreSQL（`DATABASE_URL_TEMPLATE` + compose postgres + SQLite→PG 迁移；kb-alpha 已迁移 73 docs / 39,870 chunks）
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
- [x] L1/L2 部署与 KB 验证（kb-alpha reindex 完成；acceptance 11/11；浏览器 Agent 模式已验证）
- [x] 修复 `AnswerEngine` 把 "List/Summary" 研究问题误判为 inventory
- [ ] L2 流式输出（SSE / 逐 token）
- [ ] 独立 `softwiki-agent` 容器，pin opencode `1.18.35` + 升级冒烟测试


### M5 — Wiki Prompt Studio / 覆盖率
> 指南：`docs/04-guides/wiki-prompt-studio.md`
- [x] intervention 存储/组合（global/group/topic + ad-hoc）
- [x] `POST /api/wiki/preview`：指定 1–3 个 topic，写 preview 目录，canonical 不动
- [x] `POST /api/wiki/apply`：保存后可写 canonical
- [x] Prompt Studio UI：textarea、scope 保存、Preview、Apply、diagnostics
- [x] intervention hash：提示词变化强制 full rebuild；删除后恢复
- [x] 保存的 intervention 在 Generate/Regenerate 自动生效
- [x] `GET /api/wiki/coverage`：claim 覆盖率/未映射 top
- [x] 三级分类：IP 产品 / 协议 / 技术；IP 子类 CPU/NPU/AMBA/DMA/Other
- [x] alias-aware 合并页：AMBA / P/Q / System / Low Power / SoC / PL031
- [x] `__ignore__` 忽略法务/模板 topic（1,107 claims）
- [x] claim 覆盖率从 3.4% 提升到 **15.94%**（effective 17.80%）
- [x] 12 个策展页面已生成（IP 6 + 协议 3 + 技术 3）；Cortex-M55 已验证
- [x] 旧页面归档到 `exports/wiki/archive/`；PL301 标记 no_docs；DMA 留空
- [x] 回归：pytest 71 passed（taxonomy/prompt），web build 通过
- [ ] 自动重建接线（index/ingest 后按策展范围）
- [ ] 继续 alias/新 canonical 收编 7,781 unmapped
- [ ] PL301/NIC-400 等 IP 文档补齐；DMA/其他产品后续加入


### M6 — 知识系统（Claim / 冲突 / 版本 / 投影）
> 原则：`docs/02-design/knowledge-system-philosophy.md`
> 计划：`docs/05-roadmap/knowledge-system-plan.md`
> 术语：LLM-Wiki = 叙事层；WikiArtifact = 页面工件；Static Wiki Site = 发布层

**P0 — 事实层可裁决（v0 已完成）**
- [x] A Schema v2：ClaimEvidence / CanonicalClaim / claim status / Contradiction / Adjudication / WikiArtifactState
- [x] B Ingestion/versioning：family_id / revision / supersedes；同 URL 新内容建新版本
- [x] C Claim canonicalization v1：确定性 key，10,573 raw → 9,766 canonical + 10,573 evidence
- [x] D Version supersede：同 family 新 revision 自动；合成用例通过
- [x] E Conflict rules v0：单数值/模板一致才判；当前真实库 0 冲突（保守）
- [x] F Adjudication API + WebUI Conflicts 面板（accept/keep/error/needs-evidence/reopen）
- [x] G Conflict-aware AnswerEngine：active/disputed + 冲突上下文 + 不静默选边提示
- [x] N Metrics：`/api/knowledge/metrics`；Conflicts 面板显示

**P1 — 投影层可控**
- [x] H GraphEdge 挂 claim/evidence/status：status 列 + canonical_claim_id 回填 6,994/7,211；查询过滤 active
- [x] I Timeline 挂 claim/evidence：status 列 + canonical_claim_id 回填 599/639；查询过滤 active
- [x] J WikiArtifact stale / rebuild queue / Current-History-Disputed：state/stale/UI banner/durable queue + auto worker/History API+UI/Disputed 小节
- [x] M Chunk dedup：检索按文档 + normalized chunk text 折叠重复
- [~] K Wiki 规模策略：三级分类 + 12 页已重建；Tier 1/2 代码未做

**P2 — 大库与自动化**
- [~] L Near-duplicate documents：bottom-k MinHash 报告 6 对候选；不自动合并
- [~] E NLI/LLM conflict detection：`knowledge_v2_nli.py` 候选 + LLM judge + 缓存；已确认 1 个 DATA1/DATA2 位重叠冲突；未定时/未评测
- [x] 自动文档家族/revision（v0：URL/source+title + published_at）
- [x] 冲突严重度/成本/队列优化（v0：high/medium；人工队列）

### M7 — Chat UX（只参考 opencoco 的 chat）
> 设计：`docs/02-design/chat-ux.md`（业务流沿用现有实现）
- [x] P0 后端：`/api/agent/events` SSE（session 过滤 + 心跳 + `/global/event`→`/event` 回退）
- [x] P0 后端：`/api/agent/prompt`（`prompt_async`）、`/api/agent/sessions`、`/api/agent/session/{id}/messages`
- [x] P0 前端：Next SSE 直转、parts reducer、工具卡片、停止/重试、历史恢复、会话选择
- [x] Quick 分支保持原样；ChatMessage 接入 GFM 表格
- [x] 验证：pytest 95 passed；`npm run build` 通过；假上游实测 SSE 0.6s/条不缓冲
- [ ] 真机端到端（build-host / trial-host：真实 opencode 事件 schema、6111）
- [ ] permission / question 内联卡片（默认只读，暂不出现）
- [ ] P1 Quick 阶段事件（检索→融合→生成→引用）
- [ ] 会话按 KB 打标、删除/重命名、Last-Event-ID 续传
- [ ] P2 wiki 专属：pin 文档/claim、答案存 wiki/claim、右侧 claims/conflicts 上下文

### M9 — 反代身份接入（proxy 模式，2026-11-20）
> 文档：`docs/03-operations/auth-proxy.md`；设计：`docs/02-design/auth-oidc.md`
- [x] `SOFTWIKI_AUTH_MODE=proxy`：从 `X-Auth-Request-User/-Groups` 取身份，走既有用户表/组映射/角色/kb_scope
- [x] `softwiki/identity/proxy.py`：信任边界在代码内强制（只认 `SOFTWIKI_TRUSTED_PROXIES`，不看 `X-Forwarded-For`）
- [x] `softwiki/netacl.py`：来源 CIDR 白名单，默认关闭，配置错误 fail-closed
- [x] MCP 侧 `NetworkAllowlistMiddleware`；web `/api/agent/events` 转发 `x-auth-request-*`
- [x] `docker-compose.auth-demo.yml`：Casdoor（含微信登录）+ oauth2-proxy forward-auth
- [x] 测试 `tests/test_identity_proxy.py`(8) + `tests/test_netacl.py`(9)；`scripts/e2e_proxy_auth.py` 实测
      trusted authenticated=True / forged rejected=True
- [x] `scripts/verify_proxy_headers.py`：对接方一条命令验收身份 header
- [x] 对接契约写入 `docs/03-operations/auth-proxy.md` §6.5：
      备案/域名/微信主体审核属对接方，我们只提供 header 契约 + 组映射 + 审计
- [x] 轻量示例已部署 trial-host：`deploy/auth-demo/`（Authelia + nginx），
      6190 应用 / 6191 登录页；实测 alice->wiki-work、bob->wiki-study、
      未知组 pending、外部直连伪造 header 无效
- [ ] 生产栈（6108/6109）实际启用认证（等 CIDR / 客户 IdP 参数）

### M11 — javis 升级到最新版（单机版，2026-11-23）
- [x] 旧 systemd `softwiki-api/mcp/web` 停用并 disable（它们占着 6200/6100/6108，
      导致 CI 每次部署都因 `bind: address already in use` 失败）
- [x] Docker Compose 接管三端口；`armkb` 迁到 `workspace/stacks/javis/armkb`
- [x] deploy service 补 `SOFTWIKI_STACK_ROOT` / `SHARED_CONFIG` / `AUDIT_DIR` / `WIKIWEB_*`
- [x] 单机版验证：`mode=off`、`superuser=true`、`role=wiki-admin`；
      数据完好 73 docs / 39,870 chunks / 10,573 claims；新功能 `/api/wiki/pages` 可用（436 候选）
- [x] 徽章不再截断为 `9999+`（10,573 显示完整数字）
- [x] LLM-Wiki 候选接口性能：436 个实体逐个 COUNT（33s）→ 一条 VALUES join + 120s 缓存
      （冷 11.9s / 命中 0.03s）
- [x] armkb 首次生成实体页：12 个 subject → 87 页，6.6 分钟，0 失败
      （把 `armkb/config/model_profiles.yaml` 的 wiki_compilation 从 deepseek-v4-pro
      换成 deepseek-v4-flash，单页从 ~120s 降到 6–10s；原文件备份为 *.bak-20261123）
- [x] javis 的 wiki 生成改走 trial 同一套网关：`oneroute` + `deepseek-v4.1-flash`
      （`DEEPSEEK_API_KEY` 进 `.env`；`model_profiles.yaml` 的 wiki_compilation 不再带明文 key）
- [ ] `model_profiles.yaml` 的 `cheap_extraction` / `high_quality_analysis` 仍是明文 key

### M12 — LLM-Wiki 全量生成 + 人工干预（2026-11-23）
- [x] `config/wiki_subjects.yaml`：subject 级 `ignore`（不建页/不进候选/不参与增量）与 `locked`（人工页不被覆盖）
- [x] UI：候选列表每行 `✕` 一键忽略；API `GET/POST /api/wiki/subject-rules`
- [x] 三态界面：尚未建立（Start generation）/ 正在建立（队列数，刷新不加速）/ 已建立（自动更新提示）
- [x] 增量自动：worker 每 300s 跑一次 `reconcile(allow_initial=False)`，**不会自动 bootstrap**
- [x] 批量脚本支持并发（`wiki_build_batch.py URL limit skip_over workers`）
- [x] armkb 全量生成：409 ok / 2 timeout（服务端仍完成），**407 subjects / 957 pages**
- [x] 忽略无意义实体：Arm / ARM / ARM Limited / All / Cambridge / England / RAM（共删约 150 页）
- [!] 仍有超大概念页：ROM 726/30 页、SPE 686/28、AXI 437/18、AHB 416/17 —— 是否忽略由人工决定

### M13 — Graph × Claim × Wiki 联合检索（2026-11-24）
> 设计：`docs/02-design/graph-claim-wiki.md`
- [x] 设计文档：Graph=路由 / Claim=事实 / Wiki=叙事 / RAG=原文的分工与验收
- [x] `softwiki/intelligence/graph_claim.py`：实体链接（NFKC 归一化 + ASCII 边界 + 中文 n-gram + 度数）、1–2 跳扩展、canonical claim 挂载（active/disputed）、非 stale wiki 匹配、可解释加权排序、降级为空
- [x] AnswerEngine 接入：图上下文优先 CGW（LightRAG → LIKE 仅兜底）；图挂 claim 合并进 claims 上下文（去重、带页码）；wiki 用 subject 页
- [x] 中文检索修复：`query_terms()`（4/3/2 字 n-gram）替换 `question.split()`，claim / graph / timeline 三处共用
- [x] `tests/test_graph_claim.py` 10 项；相关回归 31 passed
- [x] 本机 `lsl-kb` 真实验证：`LSL 脚本怎么写` → 实体 LSL（度数 911）→ 80 条边（此前中文命中 0）
- [ ] 评测集：20–30 条 golden questions（期望实体/路径/引用），graph on/off 对比
- [ ] P1：`source_entity_id`/`target_entity_id` + 别名合并 + 边去重与置信度
- [x] 部署 trial-host（2026-11-24，镜像 `456f8d07e45e`；两栈 + swagent 已重启；projections backfill 6,850/8,179 与 10,042/12,067；`/api/ask` 17 sources 正常）
- [x] build-host 部署已收口到 CI（2026-11-24：push `a3124d4`，CI 部署通过，验收 24 题）
- [ ] 真实问答质量观察（评测集建好后对比 graph on/off）

### M14 — 前端助手侧栏补齐（trial-host，2026-11-24）
- [x] 定位：trial 的 `web/` 是手工拷贝的非 git 分支（带 i18n），停在 11-20；后端一直新 →
      界面没有助手，API `/api/agent/projects` 却 200
- [x] 同步 6 个前端文件（`app/page.tsx`、`Sidebar`、`RoleSelector`、`TimelinePanel`、
      `WikiPagesPanel` + 新增 `AgentSidePane`），备份 `backup-20261124/web-src-1833.tgz`
- [x] 离线就地构建流程（trial 出口 ~130kbps、npmjs 不可达、node 基础镜像拉不动）：
      容器内 `next build`（复用镜像 node_modules + npmmirror）→ `FROM 旧镜像` 打补丁 → 两栈 force-recreate
      步骤与坑写入 `docs/03-operations/deployment-trial.md`「前端同步与离线构建」
- [x] 验收（coffee 6108 / ai 6109）：Assistant 开关 → Work|Manage|Admin → About|Sessions|Chat；
      降级 wiki-work 后只剩 Work；真实对话返回中文答案；无 pageerror
- [ ] 新组件文案仍英文（trial i18n 未覆盖），与 zh 界面混排
- [ ] `web/` 仍非 git 仓库，下次前端改动仍需手工同步

### M15 — armkb Graph v2 重建（2026-11-24）
> 设计/记录：`docs/02-design/graph-claim-wiki.md` §7；演示页：`docs/04-guides/graph-studio.md`
- [x] schema v3：`entities.normalized_name/aliases/merged_into`、`entity_aliases`、`relationships.source/target_entity_id + weight/evidence_count`（幂等加列/索引）
- [x] 抽取 prompt v2（ARM 领域：类型 taxonomy、aliases、受控关系词、confidence、证据短语、端点校验、同窗口去重）
- [x] `scripts/graph_reextract.py`（多文档并行抽取 → 串行 canonicalize → 孤儿清理 → 归一）
- [x] 504 治理：`create_chat_completion` 3 次退避重试、`LLM_TIMEOUT_SECONDS`、图抽取最终失败返回空（禁止启发式污染）、`scripts/graph_topup.py` 补图
- [x] `scripts/graph_normalize.py`：同名合并、别名物化、端点回填、跨文档 weight
- [x] 检索：实体链接走 alias/normalized，边优先 id，排序含 weight；`/api/graph/{search,entity,path}`；overview 按 id 聚合
- [x] `/graph-studio` 演示页（力导向、路径高亮、实体卡、claim、wiki）+ 侧栏入口
- [x] `scripts/graph_acceptance.py` + `graph_golden.yaml`（24 题；实体命中率/术语覆盖/p50/p95）
- [x] armkb 全量重抽（73 篇；分 1–38 / 39–47 / 48–73 三段并行；trial oneroute）
- [x] `graph_topup.py --all` 全量补图：73 篇只重跑图抽取，relationships 4,572 → **9,491**（8,957 挂 claim）
- [x] 投影 + 归一 + 别名治理：claims 15,465 / canonical 14,704 / entities **9,256**（合并 634、别名 2,244）/ relationships **9,491**（8,957 挂 claim，avg weight 1.12）/ events 743
- [x] wiki：旧 929 页归档，重建 233 页；重点实体已有 wiki
- [x] 验收：24 题实体命中 100%，术语覆盖 **82.0% vs 40.3%**，p50 **62ms** / p95 **79ms**（补图 + 正则缓存后）
- [x] 部署 javis：2026-11-24 已 push 并走 CI，源码/镜像/仓库三方一致（tag `a3124d4`）
- [x] 修复 CI 静默失败：`~/.docker/buildx/current` 被手工 `sudo docker build` 写成 root 所有，
      `User=faye` 无法写 → 每 3 分钟 FAILURE 但线上跑旧镜像（详见 `deployment-build.md`）

### M16 — trial 两库 Graph v2 + 助手中文化 + agent 权限（2026-11-25）
> 记录：`docs/03-operations/deployment-trial.md`「Graph v2 + 助手 i18n 全量部署」
- [x] 代码：api/web 全部同步到 trial（补丁镜像，离线构建；api `471e4af3f03c` / web `1f629f897dba`）
- [x] 助手侧栏 i18n（en/zh/ja）：项目名与说明、About 三项、会话、输入框、`role.workingAs`
- [x] 三个 agent 的工具级权限：所有 profile deny bash/edit/write；study/research 只读；
      work 可 propose；manage 可 ingest/index/build；admin 只保留基础 deny（`tests/test_agent_permissions.py` 7 项）
- [x] 清掉上一版抽屉遗留的 `.agentBtn` 死 CSS（9 个 module.css）
- [x] 备份：`backup-20261125/`（coffee 5.9M / ai 8.6M / workspace 70M）+ 镜像回滚 tag
- [x] coffee 全量重抽：185 篇，0 失败；7,144 claims / 7,086 canonical / 8,508 entities / 8,496 rel / 2,179 events
- [x] ai-history 全量重抽：160 篇，1 篇失败后修复补跑；10,055 claims / 10,033 canonical / 12,238 entities /
      12,145 rel / 3,137 events
- [x] wiki 自动重建：coffee 119 done / ai 166 done（claim 变化自动入队，worker 串行）
- [x] 修复 `claim_extractor` 的 NOT NULL 崩整篇 bug（缺 text 的 claim 丢弃并计数）+ 回归测试
- [x] 修复度数 key 不一致（`graph_claim._degrees` 用 separator-only key，实体用剥后缀的 canonical key
      → "AeroPress, Inc." 度数恒 0；trial coffee 实测 0 → 38）+ 回归测试；push `ad60d95`
- [x] javis CI 同步到 `ad60d95`，验收复跑 100% / 82.0% / p50 61ms / p95 82ms
- [ ] trial 无 CI，本轮是手工同步；后续仍要手工

### M17 — 向量后端迁移 pgvector（2026-11-25）
> 文档：`docs/03-operations/storage.md`「向量后端：文件 vs pgvector」
- [x] `PgVectorStore` + `LocalVectorStore` 门面：`SOFTWIKI_VECTOR_BACKEND=pg|file`（默认 file，可回退）
- [x] `chunk_embeddings`（FK cascade）+ UPSERT 写 + cosine ANN + delete/reset；索引 HNSW(m=16,ef=64)
- [x] `scripts/migrate_vectors_to_pg.py`：npz → 过滤孤儿 → 分批 upsert → 索引 → 数量 + recall@50 校验
- [x] 查询期 `hnsw.ef_search=max(40,k*4)` + `enable_seqscan=off`（否则 top-50 召回 80%、走 seq scan 400ms）
- [x] javis armkb：39,870 live / 39,870 孤儿；recall@50 **99.7%**；pg 查询 **4.7ms**（file 348ms / 加载 614ms）
- [x] trial 两库：coffee 3,489 / ai 5,497，recall **100%**，p50 4.2/4.4ms；`/api/ask` 21/19 sources 正常
- [x] 部署：compose `POSTGRES_IMAGE` 可覆盖；javis CI `.env`、trial `.env/.env.ai`；
      trial 通过 `docker.1ms.run` 镜像源拉 pgvector 后 `docker tag`
- [x] 备份：`backup-armkb-before-pgvector-20261124-192809.sql.gz`、`backup-{coffee,ai}-before-pgvector-20261125-121407.sql.gz`
- [ ] 文件后端 npz/pkl 暂留回退；确认稳定后可归档（trial 41/65MB、javis 936MB）

### M18 — 三处运维/质量欠账（2026-11-25）
- [x] wiki 任务租约：`running` 每 60s 心跳；worker 启动/每轮回收超过
      `WIKI_TASK_STALE_MINUTES`（默认 30）的 running → pending（未超 max_attempts）或 failed。
      javis 实测回收 5 个卡了一天的任务，日志 `reaped 5 stale running task(s)`
- [x] LightRAG 开关：`processor._get_lightrag_adapter()` 尊重 `SOFTWIKI_DISABLE_LIGHTRAG`，
      入库与查询同开关（测试覆盖 disable / 未 disable 两条路径）
- [x] `scripts/deploy-trial.sh`：preflight → pg_dump → 同步源码 → api-fast 构建 →
      两栈 recreate → swagent 重启 → /api/health + /api/kb + web 检查；
      支持 `--check` / `--skip-build` / `--skip-backup` / `--migrate-vectors`。
      已用它实际部署 trial（备份 `20261125-011113`），两栈 healthy
- [x] 发现：`git.softkitty.me`（homelab git 公网反代）**trial 可达**（~7s，repo 为
      public 且 HEAD=`9d4493c`）→ trial CI 技术上可行，待决定是否启用

### M19 — ARM Wikiweb + 试用库评测（2026-11-25）
- [x] `scripts/wikiweb_build.py`：确定性静态门户（复用 Coffee 的 CSS/外壳），
      内容来自 canonical claims / events / relationships / documents；
      摘要取 LLM Wiki 页首段（不调 LLM）；slug 冲突去重；测试覆盖
- [x] javis armkb 门户生成：**300 页 / 12 分类**，`/wikiweb/armkb/` 200；
      摘要改为首段并去掉 `[N]` 引用
- [x] 重要坑：Next 在启动时枚举 `public/`，生成后必须**重启 web 容器**，否则 404
- [x] trial 两库 golden set（各 20 题）并跑检索验收：
      coffee 实体命中 75% / 覆盖 **80.0% vs 46.7%**；ai 95% / **88.3% vs 56.7%**
- [x] 修复 trial 图未挂 claim：`knowledge_v2_projections.py` 回填
      coffee 7,355/8,496、ai 10,385/12,145，之后 acceptance claims 0 → 16
- [x] SPE 失败任务重置（attempts 0/max 5）并重新入队，heartbeat 进行中
- [ ] trial 两库门户仍为用户 agent 生成版（不覆盖）
- [x] SPE 已生成（attempts 1，done）；批量补建 100 个候选：99 ok / 1 failed（SP 超时）
- [x] SP 重试成功；批量补建完成：subject **542 个 / 1,933 个页面文件**，failed 0
- [x] 门户最终生成：**600 页 / 13 分类**，`/wikiweb/armkb/` 200

### M20 — LLM 故障治理（2026-11-26）
> 事故：oneroute 余额耗尽（剩余 $0.037，单页预扣 ~$0.06）→ 403；自动补队列每轮重试
> 导致 8,199 个 failed 任务，并写坏 `wiki_rebuild_tasks` 的 btree 索引。
- [x] 止血：`WIKI_AUTO_ENQUEUE_MISSING=0`、删除 8,199 failed 行、`REINDEX TABLE`
- [x] 失败窗口：`WIKI_BACKFILL_RETRY_HOURS=6`，近期失败的 subject 不再自动重排
- [x] **provider 熔断**（`intelligence/llm_health.py`）：401/403/额度/鉴权 = fatal，
      立即熔断（默认 900s）；5xx/超时 3 次熔断 60s；成功复位；
      熔断期间 `create_chat_completion` 直接抛 `ProviderUnavailable`，不发请求
- [x] 队列语义修正：provider 失败时任务回 `pending`（不消耗 attempts/不标 failed），
      worker 熔断期间暂停领取，`AUTO_ENQUEUE` 跳过
- [x] `/api/knowledge/metrics` 暴露 `llm_provider`（open/reason/retry_in/strikes）
- [x] 充值后恢复：probe ok，熔断 closed；补队列重新入队 **189**，3 workers 运行中
- [x] 剩余 subject 跑完（pending/running/failed 均 0）；wikiweb 600 页；
      golden 复测：实体命中 100%，术语覆盖 **84.7% vs 40.3%**，p50 73ms / p95 89ms

### M10 — 内置 admin 账号（2026-11-22）
> 文档：`docs/03-operations/auth-proxy.md` §6.7
- [x] `softwiki/identity/localauth.py`：scrypt 哈希（独立盐）、首启创建、按 IP 限速、审计
- [x] `POST /api/auth/password`（加入免认证路径）；`scripts/set_admin_password.py` 改密码
- [x] 无默认密码：未设 `SOFTWIKI_ADMIN_PASSWORD` 则生成随机密码，启动日志打印一次
- [x] 测试 `tests/test_localauth.py` 11 项；`scripts/e2e_admin_login.py` 实测
      登录得 wiki-admin、错密码 401、限速生效
- [x] 反代放行应急入口：nginx 对 `/api/auth/password|me|providers` 不走 auth_request
      （否则 provider 挂掉时无法登录）；代价是该接口公网可达，靠限速 + 强随机密码
- [x] 单机版不创建内置账号（`off` 模式下所有人已是本机管理员，多一行只会让 Users 面板困惑）
- [x] 反代场景下限速/审计改用真实客户端地址（仅当来源是受信反代才采信 `X-Forwarded-For`）
- [x] 三场景手册：`docs/03-operations/user-system-manual.md`
- [x] demo 栈补齐 WebUI（web 容器 + 网络别名 `api`，因为 Next rewrite 目标在构建时固定）
- [x] **修复两个真 bug**（proxy 模式实测暴露）：
      ① `auth_middleware` 早于 `role_middleware` 执行，非豁免路径全 401；
      ② `auth_enabled()` 只认旧开关，`AUTH_MODE=proxy` 时匿名仍可访问 API；
         且中间件里还留着旧 session-token 分支，会拒绝新身份层
- [x] demo 栈改成**一个实例服务两个真实库**（私有 postgres + 两个 workspace 拷贝），
      按用户 `kb_scope` 分配：alice→coffee、bob→ai-history、admin→两个
- [x] 新增 `POST /api/kb/switch` + `LocalUser.active_kb`（按用户记住当前库，请求级生效）
- [x] 前端库选择器：可原地切换（auth 开启时），否则回退跨端口跳转
- [ ] WebUI 登录页（内置 admin 仍只有 API 入口）
- [ ] 多进程下限速为每进程独立（单实例部署可接受）

### M8 — LLM-Wiki 粒度重构（2026-11-20）
> 设计：`docs/02-design/wiki-page-granularity.md`
- [x] 试点确认阈值：23 条清楚 / 129 条退化；一页上限固定 **25**，超限拆页不截断
- [x] `softwiki/wiki/subject_pages.py`：subject 枚举（关系度 ≥5）+ 母题排除（覆盖 ≥15% 语料）+ 拆页
- [x] 禁止静默截断：超过上限要么拆页要么报错，每页记录 `claims_covered/total`
- [x] API `GET /api/wiki/pages`、`POST /api/wiki/pages/build`、`GET /api/wiki/pages/{slug}`
- [x] WebUI **Wiki Pages** 面板：搜索 + 类型筛选 + 分页 tab + `25/144 claims` 徽章
- [x] `scripts/wiki_build_batch.py` 批量生成
- [x] 测试 `tests/test_wiki_subject_pages.py` 9 项；全量 183 passed
- [x] 部署 trial-host 两栈，批量生成 coffee / ai-history
- [x] 侧栏分组重构（Home / Knowledge / Assist / Contributor / Admin）；`wiki` 面板下线，`wikipages` 更名 **LLM Wiki**
- [x] documents / claims / LLM Wiki 分页（服务端 `limit/offset`；claims 6,691 条不再全量渲染）
- [x] 徽章显示完整数字；表格列宽 / 行距优化
- [x] `AdminPanel`（Users 放行 + 审计日志），仅 admin 可见
- [x] 角色驱动导航可见性：Contributor 组 work+，Admin 组 admin
- [ ] `topics.yaml` 接入为策展覆盖层
- [ ] 增量重建（claim 变更只重生成受影响 subject）
- [ ] 文档标题清洗（`Document` / `Study authors` 占位名）
- [ ] 与 wikiweb 门户对接（门户由 agent 生成，另行讨论）
- [ ] Home 跨 KB 总览（各库统计 + 日志）
- [ ] KB 管理面板（注册表 / 卸载脱钩）
- [ ] 贡献者笔记审核入库（manage/work 可见）

### M21 — 界面重整（2026-11-26）
> 设计：`docs/02-design/ui-information-architecture.md`（✅ frozen）
- [x] 侧栏改为「总览 / 知识库 / 管理 / 会话」，删除自动折叠（只手动）
- [x] 导入/冲突改为单项 `wiki-work+`（不再整组隐藏）；管理组 `wiki-admin+`
- [x] 新增「用户」入口（AdminPanel 之前无法进入）；「新建库」更名「知识库管理」
- [x] 会话列表常驻侧栏底部；会话按知识库隔离（`softwiki_sessions:<kb>`）
- [x] 助手按钮移到主区右上，与主题按钮同簇（不再重叠）
- [x] 图谱：Graph Studio 组件化内嵌（`GraphStudioPanel`），删除外链项；
      `/graph-studio` 保留为薄包装
- [x] 图谱交互修复：仅中键平移、左键空白不动作、滚轮以光标为锚点、新增 fit 按钮
- [x] 图谱力学修复：斥力下限/上限、速度上限、阻尼 0.9、中心引力、软边界、
      动能停帧；展开节点以父实体为锚、视野外自动 fit
- [x] Wiki 面板：门户内嵌 + 「页面与生成」tab（原 LLM Wiki 面板收编）+ 助手入口（落 manage）
- [x] 对话默认只走 agent；Quick 降为对话空状态的次级入口
- [x] 首页改为跨库总览：新增 `GET /api/kb/stats`（30s 缓存，逐库读 DB，
      不可用库灰显）；`tests/test_kb_stats.py` 2 项通过
- [x] 建库自动建数据库（SQLite 建文件 / PG 建库+建表）+ `POST /api/kb/{name}/provision` 补建
- [x] `/api/kb/switch` 在 off 模式放行（原来 401，新库可用了也切不过去）
- [x] 建库/补库后侧栏下拉自动刷新（`softwiki:kb-changed` 事件）
- [ ] 门户重建按钮（需后台任务 API + 重启 web）
- [ ] 侧栏会话与面板内 agent session 选择器合并
- [ ] 旧全局会话 key 迁移（升级后历史会话不显示）
- [ ] 删除已无引用的 `GraphPanel.tsx`

## Pending issues / Blocker

- [!] **trial-host embedding 上游 504（2026-11-20 发现）**：`oneroute` 的 `/v1/embeddings` 返回 `Error code: 504`，单次耗时 **185s** 才失败；容器日志 `[rag] embedding unavailable, using BM25 only`。因此 `/api/ask` 会先卡 185s 再降级，实测 200s 超时未返回。
  - 影响：新入库无法向量化、ask 极慢；检索退化为 BM25。
  - 不是本次改动引入（stash 对照确认）；chat 通道正常（8.6s 返回）。
  - 需要换 embedding 供应商或用本地 `nomic-embed-text`（Ollama 已装）。

- [x] **真实 PDF**：已提供 81 篇 ARM 技术文档。
- [~] **出站 LLM/embedding**：当前用 OpenAI + DeepSeek；学校内网是否允许出站仍未确认。
- [x] **测试基线**：86 passed（离线；含 knowledge v2 / NLI / citation / permissions / cleanup / embedding / thinking）。
- [x] **数据库**：PostgreSQL 已切换并迁移（SQLite 作为回退）。
- [ ] **OCR 范围**：扫描版 PDF 未支持。
- [x] build-host deploy key 已加入 Forgejo。
- [x] **embedding 已修复**：OpenAI `text-embedding-3-small`（1536 维），分批 + 并发 + TPM 限速。
- [x] **切流**：Docker 接管 `6200/6100/6108`，旧 systemd 已 disable。
- [x] **CI timer 已重新启用**。
- [x] **kb-alpha 全量索引完成**：`{"status":"success","indexed_chunks":39870}`；`search`（页码）、`ask`（页码引用）、`/api/report` 均已验证。
- [x] **kb-alpha 数据**：73 篇 / 39,870 chunks / 10,573 claims / 4,165 entities / 7,211 relationships / 639 events。
- [x] **kb-alpha 窗口化重抽完成**：73/73；最终 10,573 claims / 4,165 entities / 7,211 relationships / 639 events；acceptance **11/11**。
- [!] **Workflow 目前只是 prompt 注入**：没有自动路由/verifier 执行；`workflows.yaml` 的 `modes` 字段仍未使用。
- [!] **TUI 不是沙盒**：调用系统 opencode，配置/会话隔离，但文件系统/网络是用户权限；打包/升级见 `docs/05-roadmap/agent-web-plan.md`。
- [!] **TUI 默认不读 KB**：`agent_soul.md` 禁止 `softwiki_search/ask/retrieve`；Agent Web 已新增 `wiki-research` 并开放只读 KB 工具。
- [x] **kb-alpha reindex 完成**：2026-10-24 agent 误调 `softwiki_rebuild_index` 后重跑全量索引；39,870 chunks，`softwiki_search` / `softwiki_ask` / acceptance 11/11 已验证。已用 opencode permission 禁止写工具。
- [ ] **Agent source 标题**：部分 PDF 抽取标题为 `Untitled Document`；页码有效，标题清洗待做。
- [ ] **Agent SSE**：L2 目前是轮询非流式；逐 token/工具事件输出待做。
- [x] **Agent 长请求**：Next rewrite 默认 30s 超时导致 33s 的 agent 回答被前端误报 `Invalid response`；已设 `experimental.proxyTimeout=300_000`，并修正错误文案。
- [x] **Agent source 元数据**：从答案引用解析出的 source 之前 `Unknown / 0%`；现用 KB 反查 `source_name`/日期/页码/摘录，无检索分数的 source 隐藏百分比。
- [x] **Agent 链接**：`/agent` 同源 307 → 当前 host:6111，不再写死 localhost。
- [ ] **Agent Session / 沙盒 / 审核**：设计见 `docs/05-roadmap/agent-session-sandbox-plan.md`；P0/P1 待确认后开工。
- [x] **Knowledge v2 v0 已落地**：ClaimEvidence / CanonicalClaim / status / Contradiction / Adjudication / WikiArtifactState；迁移脚本与备份完成。
- [x] **Graph/Timeline claim 投影**：6,994/7,211 relationships、599/639 events 已挂 canonical claim；status 过滤。
- [x] **Chunk dedup**：HybridSearcher 按 document_id + normalized text 折叠重复。
- [x] **Wiki 自动重建**：durable `wiki_rebuild_tasks` + API worker；claim 变化/裁定/冲突扫描自动 enqueue；任务测试 done。
- [~] **NLI/LLM 冲突检测**：`knowledge/nli.py` + `/api/knowledge/nli/scan` + `ClaimPairJudgement`；已开 1 个 DATA1/DATA2 位重叠冲突（medium，2 claims disputed）；尚未定时/评测。
- [~] **近重复文档**：MinHash 报告 6 对候选（M55/M85、ADI v5/v6 等），不自动合并。
- [~] **Graph/Timeline 版本继承**：adjudication 后已 reproject status；版本链/supersedes/evidence 多对多未做。
- [~] **Structured claim**：`subject/predicate/object/qualifiers` 字段 + 可选 LLM 结构脚本；已结构 569 条，未全量。
- [x] **Conflict UI/API**：分页 + status/severity/type/topic 过滤 + evidence drawer。
- [x] **角色 / capability**：`permissions.yaml` + Web role cookie + MCP role header + API/MCP guards；无 key，内部信任。
- [x] **MMR**：HybridSearcher 增加轻量 MMR 去冗余。
- [x] **Citation check**：`/api/ask` 返回 `citation_check`（unknown/unused/warnings）。
- [~] **Wiki Artifact History**：`wiki_artifact_versions` + History API/UI；旧页面归档，current 覆盖。
- [x] **Wiki 自动重建**：canonicalize/裁定后自动 enqueue；worker 串行重建，失败重试 2 次。
- [!] **Claim 覆盖率 15.94%**：1,685/10,573 mapped；7,781 unmapped；1,107 ignored；effective 17.80%。Top unmapped 是零散技术/文档 topic（unpredictable-behavior、ppu-register-summary、software-tests、ip-xact 等）。
- [x] **Wiki 页面数量**：12 个策展页面已用 canonical claims 重建；stale 0。
- [~] **remote MCP 写工具**：现在按 role header 拦截；无 key 时可伪造，内部信任；产品化需 API key/token。
- [ ] **Postgres 备份**：文档已写 `pg_dump`，尚未纳入 `scripts/backup.sh`。
- [!] **密钥明文**：`model_profiles.yaml` 仍有明文 DeepSeek key；OpenAI key 曾在聊天暴露，建议轮换。
- [ ] **TLS/反代**：build-host 无 Caddy/Nginx；试用先用 HTTP。
- [x] **认证/权限**：demo 阶段明确不做（代码保留，默认关闭）。
- [ ] **trial-host 汉化未入库**：前端 i18n（zh/en/ja，311 keys）只在 trial-host 源码里，已构建运行；无 git，备份 `backup-20261116/web-src-bak-20261116-1030.tgz`。待定是否收编，缺口见 `docs/03-operations/deployment-trial.md`。

## 下一步（NEXT）

0.1 **trial-host 部署已完成（2026-11-19 部署 / 2026-11-20 重启复核）**：两栈都已跑新代码，12/12 验收通过；详见 `docs/03-operations/deployment-trial.md`「2026-11-19 部署」。
   **上线后待测**：SWAgent 真机对话、Wiki/Conflicts/Report 回归。图谱页与建库面板已用真实浏览器冒烟（`scripts/ui-smoke.mjs`）。
   **剩余遗留**：`pip install -e .` 在新构建中报 `ResolutionImpossible`，本次用 `deploy/Dockerfile.api-fast` 复用旧依赖层绕过；根因未定位，下次重建依赖前要查。
0.2 **身份接入 / 权限（2026-11-19 已实现）**：`docs/02-design/auth-oidc.md`。
   已落地：权限 fail-closed、审计日志、超级用户窗口（默认关闭/仅本机/TTL/二次认证）、OIDC + 微信 adapter、本地用户表 + 组映射 + 三态、`kb_scope` 过滤、降级工作模式、知识库注册表 + 建库向导、图谱子图 API 与页面重写。
   全量测试 **175 passed**（基线 111）；`web` 构建通过。
   **剩余**：管理面 UI（目前只有 `/api/admin/*`）、pending 用户放行界面、标准 OIDC 授权码流程（当前走 `claims` 路径）、超级用户状态多进程存储。
0.3 **trial-host 端口暴露**：现在是 `off` 模式且公网可达，等价于任何人都是超级用户。
   **已有两条可用的收口手段**（2026-11-20）：
   - `SOFTWIKI_ALLOWED_CIDRS`：应用层来源白名单（`softwiki/netacl.py`），默认关闭，写错则拒绝所有人；
   - **proxy 模式**：`SOFTWIKI_AUTH_MODE=proxy` + oauth2-proxy/Casdoor，softwiki 只读受信 header，
     协议层交给反代。演示栈 `docker-compose.auth-demo.yml`，文档 `docs/03-operations/auth-proxy.md`。
   仍待办：trial-host 上实际启用（需要 operator 提供允许的 CIDR / IdP 参数）。
0.35 **Wiki 静态门户生成器（未做）**：门户已按库放进 `workspace/<kb>/exports/wikiweb/` 并与 `kb_scope` 隔离，但仍是**静态快照**——Wiki 重建后不会更新。需要 `softwiki wiki site`：从 canonical claims + wiki 产物渲染 HTML（index / all / about / category / timeline / `search-index.json` / `assets`），可挂到已有 `wiki_rebuild_tasks` worker 之后。估 2–4 人天。
0.4 **多 KB v0 已部署 trial-host，并完成真隔离（2026-11-20）**：`docs/02-design/multi-kb.md`。
   - **第一版的问题**：两栈挂同一个 workspace 根 → 数据库隔离但**文件不隔离**，菜单里还能看到对方的库。
   - **现状**：每栈私有根 `workspace/stacks/<stack>/<kb>`；`config`（身份）与 `.softwiki-audit`（审计）单独共享挂载。
   - 验收：`6200 /api/kb` 只有 `coffee`，`6202` 只有 `ai-history`；`ask(kb="ai-history")` 从 6200 返回 **404**（不是 500）；容器内 `ls /data/workspaces/ai-history` 不存在；跨库门户 404。
   - 加库：在栈根下新建目录 + 该栈 PG 建库即可（挂的是目录，不用重建容器）。
   - `/api/kb?verify=true` 保留为诊断（目录存在但库没建时能看出来）。
   - 若要「一个栈服务全部库」，仍需合并 PostgreSQL，并处理 Hermes（一个 MCP）与 wikiweb 路径——独立决定。
0.5 **trial-host 语料已补齐**：coffee 185 篇、ai-history 160 篇，均已建索引并验证 `/api/ask`。后续可继续加来源或换更权威语料，但数量目标已达成。
0.6 **SWAgent 已恢复双实例**：coffee 6111 / ai-history 6112；AI API 已改用 `.env.ai`，active workspace 修正为 ai-history；Web KB selector 改为跨端口跳转。
0.7 **Chat UX P0 已落地**：`docs/02-design/chat-ux.md`；后端 SSE + prompt_async + sessions/history，前端 parts 流式/工具卡片/停止重试/会话恢复。下一步：build-host 真机验收（opencode 1.19.5 事件 schema），再做 P1 Quick 阶段事件。
1. **P1 收尾**：Graph/Timeline 版本继承；evidence 多对多映射；投影重算。
2. **P2 冲突召回**：structured claim 全量/按需；NLI 定时；评测集；人工队列。
3. **Claim 覆盖率**：继续用 alias/新 canonical 收编 7,781 unmapped；当前 15.94%，effective 17.80%。
4. **Prompt 调优**：用 `docs/04-guides/wiki-prompt-studio.md` 的 IP/协议/技术范例，先 preview 再 apply。
5. **Demo**：按 `docs/04-guides/demo.md` 跑 Quick + Agent + Wiki Prompt Studio；acceptance 11/11。
6. **P2**：近重复文档、NLI 冲突、自动 family/revision。

## 本 session 状态记录（handoff）

- **2026-11-26 界面重整（逐项确认后实施）**：
  - **IA**：侧栏 = 总览 / 知识库（文档、论断、图谱、时间线、Wiki 门户、导入、冲突）/ 管理（知识库管理、用户）/ 会话（常驻）。
    自动折叠已删；角色门槛改为组级 + 单品级并存。
  - **图谱**：`components/GraphStudioPanel.tsx` 为唯一实现，`/graph-studio` 只是包装。
    平移改为仅中键（原来左键 `onClick` 才写 dragRef，实际不能拖）；滚轮以光标为中心；
    力学加了距离下限、力/速度上限、阻尼 0.9、中心引力、软边界与动能停帧；
    展开以父实体为锚，视野外自动 fit，并新增 fit 按钮。
  - **Wiki**：门户 iframe 内嵌 + 「页面与生成」tab（原 LLM Wiki 面板）+ 助手入口（落 manage）；
    「重建门户」禁用并说明需脚本 + 重启 web。
  - **对话**：默认 agent；Quick 只保留空状态里的次级入口（demo 降级路径）。
  - **首页**：`GET /api/kb/stats` 汇总本实例全部可见库，30s 缓存，打不开的库标 unavailable。
  - **验证**：`npm run build` 通过；headless Chrome 实测侧栏顺序、角色门槛（work 见导入/冲突、study 不见）、
    图谱内嵌、Wiki 面板、右上按钮坐标（x=1510/1552，无重叠）；`pytest tests/test_kb_stats.py` 2 passed。
  - **注意**：trial-host 两栈各只服务一个库，首页只会显示 1 个库（部署形态，不是 bug）。
  - **提交**：`d3ceac4` 侧栏 / `6f47ce1` 图谱 / `80e62bf` wiki 面板 / 后续一次首页 + 对话。

- **2026-11-25 ARM Wikiweb + 试用库评测 + 运维补丁**：
  - **Wikiweb**：新增 `scripts/wikiweb_build.py`（复用 Coffee 的 CSS/外壳，确定性生成）；javis armkb 已生成 **300 页 / 12 分类** 到 `exports/wikiweb/armkb/`，`/wikiweb/armkb/` 200。**关键坑**：Next 启动时枚举 `public/`，生成后必须 `docker restart softwiki-web-1`，否则 404。
  - **试用库评测**：`scripts/golden_coffee.yaml` / `golden_ai_history.yaml` 各 20 题；trial 图未挂 claim 的问题用 `knowledge_v2_projections.py` 补（coffee 7,355/8,496、ai 10,385/12,145），之后：
    coffee 实体命中 75% / 术语覆盖 **80.0% vs 46.7%**；ai 95% / **88.3% vs 56.7%**；p50 18/25ms。
  - **运维**：wiki 任务 heartbeat+reaper（javis 回收 5 个卡死任务；SPE 已重置 attempts=0/max=5 并重跑）；`SOFTWIKI_DISABLE_LIGHTRAG` 现在同时拦入库；`scripts/deploy-trial.sh` 已实际用于 trial 部署。
  - **重要状态**：javis 的 `softwiki-deploy.timer` **当前被临时 stop**（避免 CI 重启打断 SPE 生成）。SPE 完成后要 `sudo systemctl start softwiki-deploy.timer`。
  - **未完成**：SPE 仍在生成（大主题，已运行 >10min）；wiki 候选 534 个、已建 49 subject（494 缺），SPE 完成后需批量补（建议先 top 100）；trial 两库门户保留用户 agent 版本，未覆盖。


- **2026-11-25 向量迁移到 pgvector（javis + trial 两库）**：
  - **代码**：`softwiki/rag/vector_store.py` 拆成 `FileVectorStore` / `PgVectorStore`，`LocalVectorStore` 作为门面按 `SOFTWIKI_VECTOR_BACKEND` 选择；文件后端保留，改环境变量即可回退。
  - **表**：`chunk_embeddings(chunk_id FK ON DELETE CASCADE, model, dim, embedding vector(1536))`，HNSW `m=16, ef_construction=64`；写为 UPSERT，删 chunk 级联清向量。
  - **迁移**：`scripts/migrate_vectors_to_pg.py`；armkb 过滤掉一半孤儿（79,740 → 39,870），recall@50 99.7%；trial 两库 100%。
  - **性能**：armkb pg 查询 4.7ms vs 文件 348ms、加载 614ms；进程不再常驻 936MB 矩阵。存储：表 ~825MB + 索引 312MB。
  - **部署**：javis 走 CI（tag `9fca6c0`）；trial 手工同步 + `Dockerfile.api-fast` 重建 api，postgres 镜像换 `pgvector/pgvector:pg16`（trial 经 `docker.1ms.run` 拉取后 tag）。两栈 api/mcp 已 recreate，swagent 已重启。
  - **关键坑**：查询必须 `SET LOCAL hnsw.ef_search=max(40,k*4)` 且 `enable_seqscan=off`，否则召回只有 80%、耗时 400ms。
  - **回滚**：文件后端 + 原 npz 仍在；`SOFTWIKI_VECTOR_BACKEND=file` 重启 api/mcp 即可；DB 备份见上。


- **2026-11-25 trial 两库 Graph v2 + 助手中文化 + agent 权限（全量重做）**：
  - **代码**：trial 不是 git 仓库 → 整棵 `web/`、`softwiki/`、`scripts/`、`kb-templates/` 手工同步；
    api 用 `FROM 旧镜像` 只覆盖源码（依赖未变，无需 pip），web 容器内离线 `next build` 后打补丁镜像；
    swagent **不在 compose 里**，要 `docker cp` + restart 才会拿到新的 agent permission。
  - **前端**：助手侧栏接入 i18n（三语），删掉上一版上下文抽屉的 `.agentBtn` 死 CSS；Graph Studio 入口同步到位。
  - **agent 权限**：`softwiki/cli/shell.py::_agent_permissions()`，所有 profile deny bash/edit/write，
    study/research 只读，work 可 propose，manage 可 ingest/index/build，admin 只保留基础 deny。
    实测 `/agent` 接口返回的 deny 列表符合预期（两栈）。
  - **数据**：coffee 185 篇 / ai 160 篇全量重抽 + normalize，0 未解析边；claims 7,144 与 10,055，
    canonical 7,086 与 10,033，entities 8,508 与 12,238，relationships 8,496 与 12,145。
    wiki 自动重建 119 / 166 个任务全 done。
  - **修的 bug**：`claim_extractor` 把模型返回的 `text=None` 直接插库 → 整篇事务回滚。
    现在跳过缺 text 的 claim 并打印条数；ai doc 142 已补跑（14 claims / 35 entities / 38 rel / 8 events）。
  - **验收**：两栈 `/api/agent/projects` 200、`/graph-studio` 200、助手中文界面正常（工作/管理/管理员）、
    `/api/ask` coffee 2 sources、ai 9 sources，scope guard 仍能拒绝越界问题。
  - **回滚**：`backup-20261125/*.sql.gz` + `workspace-*.tgz`；镜像 `softwiki-api:pre-codev2-20261125` /
    `softwiki-web:pre-codev2-20261125`。
  - **仍欠**：trial 无 CI（手工同步）；trial 没跑 24 题 golden（那是 ARM 语料专用），
    咖啡/历史库的评测集仍未建。

- **2026-11-24 收口到 CI（javis 正规部署）**：
  - 本地 4 个未 push 提交（`d6fbe42`/`d0d3b62`/`1aa0568`/`a3124d4`）已推到 origin，CI 部署到 `a3124d4`。
  - **CI 之前静默失败了一整天**：`~/.docker/buildx/current` 是手工 `sudo docker build` 留下的 root 文件，
    `User=faye` 的 buildx 写不进去 → 每 3 分钟 `permission denied`，镜像没换、线上跑旧代码。
    已 `chown -R faye:faye ~/.docker/buildx` 并手动触发补一次；判定部署真伪要看
    `journalctl -u softwiki-deploy` + `.deploy/last-deployed-sha` + `docker images` tag 三者。
  - **验收复跑**（容器内 `scripts/graph_acceptance.py --runs 5`）：实体命中 **100%**，
    术语覆盖 **79.2%**（基线 37.5%），p50 **497ms** / p95 **530ms**，`/graph-studio` 200。
  - 源码/镜像/仓库现三方一致：javis HEAD `a3124d4`、api/web tag `a3124d4652d8`。

- **2026-11-24 armkb Graph v2 全量重建（javis）**：
  - **范围**：schema v3 + 新 ARM 抽取 prompt + 73 篇全量重抽 + 实体归一/别名 + 边权重 + CGW v2 + `/graph-studio` + 24 题验收。
  - **数据**：claims 15,465 / canonical 14,704 / evidence 15,465；entities 9,256（合并 634、别名 2,244）；relationships **9,491**（8,957 挂 claim，平均 weight 1.12）；events 743；wiki 重建 233 页（旧 929 页归档到 `exports/wiki/pages.pre-graphv2-20261124-052035`）。
  - **验收**（`scripts/graph_acceptance.py --runs 5`）：实体命中 100%，术语覆盖 **82.0% vs 40.3%**（旧 LIKE），p50 **62ms** / p95 **79ms**。
  - **部署**：最初是手动同步（api `c8a673e` / web `fitv1`）；2026-11-24 起已 **push `a3124d4` 并走 CI**，project 必须 `--project-name softwiki`（否则起出 `softwiki-ci-*` 第二套栈）；LLM 走 trial oneroute `deepseek-v4.1-flash`，key 在 `/opt/aitools/apps/softwiki/.env`。
  - **备份**：`backup-armkb-20261124-033106.sql.gz` / `backup-armkb-ws-20261124-033106.tgz` / 镜像 `softwiki-api:pre-graphv2-20261124-033106`。
  - **504 补图**：`graph_topup.py --all` 已跑完（73 篇只重跑图），关系 4,572 → 9,491；normalize/projections 重跑。
  - **已知缺口**：wiki 只重建了 233 页（60 候选 + 重点实体），其余候选未生成；别名治理目前是人工 `armkb/config/entity_aliases.yaml`。
  - **易踩坑**：批量重抽必须“并行抽取 → 串行 canonicalize”（canonical id 全局唯一）；`read_subject_page` 才能读拆页；`SOFTWIKI_DISABLE_LIGHTRAG` 仍只拦查询不拦入库。

- **2026-11-24 trial-host 助手侧栏补齐**：
  - **现象**：trial 两栈界面没有 Assistant，但 `6200/6202 /api/agent/projects` 返回 200、
    `6111/6112` swagent 在线、4 个 agent 齐全 → 纯前端问题。
  - **根因**：trial 的 `web/` 是手工拷贝的 i18n 分支（非 git），停在 11-20；M13 之后只重建了后端镜像。
  - **修复**：同步 6 个文件 → 容器内离线 `next build`（复用镜像 node_modules，npm 走 npmmirror）
    → `FROM softwiki-web:latest` 打补丁镜像 `f45b23bf01ef` → 两栈 `--no-build --force-recreate web`。
  - **验收**：Assistant 开关、三项目 tab、About/Sessions/Chat、降级后 tab 收窄、真实对话中文回答，均通过。
  - **易踩坑**：`node_modules` 不能用符号链接（turbopack 拒绝跨 root）；最终镜像缺 typescript，
    build 会自动装，必须给 npmmirror；`.dockerignore` 排除 `.next`，补丁镜像要独立上下文。
  - **仍欠**：新组件英文文案；`web/` 非 git。

- **2026-11-24 Graph × Claim × Wiki 联合检索（P0）**：
  - **背景**：此前 graph 在问答里只是 `LIKE` + `limit 10`，中文问题命中 0；claim 也是 `question.split()` 的前缀匹配。
  - **新增** `softwiki/intelligence/graph_claim.py`：实体链接（NFKC 归一化、ASCII 边界匹配避免 `rm` 命中 `arm`、中文 2–4 字 n-gram、按关系度数加权）→ 1–2 跳 BFS → 挂 canonical claim（edge 的 `canonical_claim_id` + `subject/object` 是种子实体）→ 非 stale subject wiki 页 → 可解释加权排序；任何异常降级为空。
  - **AnswerEngine 接入**：graph 上下文优先 CGW，其次 LightRAG，最后旧 LIKE；图挂 claim 合并进 claims（去重、带页码、disputed 保留）；wiki 使用 subject 页；claim/graph/timeline 统一用 `query_terms()` 修中文。
  - **验证**：`tests/test_graph_claim.py` 10 项；graph/knowledge/citations 回归 31 passed；本机 `lsl-kb` 中文问题 `LSL 脚本怎么写` 命中 LSL（度数 911）并展开 80 条边。
  - **未做**：评测集、实体 ID 化/别名合并、trial-host 部署。
  - **注意**：`SOFTWIKI_DISABLE_LIGHTRAG` 仍只拦查询不拦入库（`processor._get_lightrag_adapter()` 无检查），待单独修。


- **2026-11-20 多 KB 可用性 + 导航/列表重构**：
  - **多 KB 现状澄清**：第一版两栈共用 workspace 根，`/api/kb` 两边都列出 2 个库，但各自 PostgreSQL 独立 → 切过去 500（`database "softwiki_ai_history" does not exist`）。
  - **随后修正为真隔离**：每栈私有根 `workspace/stacks/<stack>/<kb>`（`SOFTWIKI_STACK_ROOT`），容器只挂自己的根；`config` 与 `.softwiki-audit` 单独共享。验收：6200 只列 `coffee`、6202 只列 `ai-history`；跨库 `ask` 返回 404、跨库目录不存在、跨库门户 404。数据未变（185 / 160 篇）。
  - **迁移工具**：`scripts/kb_layout_migrate.py`（默认 dry-run，校验 `.softwiki/`，打印需写入 `.env` 的变量）。trial-host 迁移前已备份 `docker-compose.yml.bak-20261120`、`.env.bak-stackroot`、`.env.ai.bak-stackroot`。
  - **`/api/kb?verify=true`**：新增 `softwiki/kb/health.py`，每库一次 `SELECT 1`（超时 3s、缓存 15s）；SQLite 额外校验文件存在（SQLite 会自动建空文件，否则假阳性）。默认 `/api/kb` 仍零 DB（设计 D1）。
  - **`meta.yaml: web_url`**：`KbInfo` 新字段，记录该库 WebUI 地址。trial-host 两库已补（6108/6109）。
  - **库选择器重写**：原来写死 `{coffee:6108, ai-history:6109}` 两张卡片，现在从 `/api/kb?verify=true` 取，不可用的库置灰并提示「N kb not served by this instance」。
  - **加库实测**：ai 栈 `mkdir workspace/probe-kb` + `CREATE DATABASE softwiki_probe_kb` → `/api/kb?verify=true` 立刻 `available=true` → 已删除目录与库。**证明每栈可独立扩容，无需改代码。**
  - **清理**：删除空残留库 `softwiki_ai`（0 张表、无对应目录）。
  - **测试**：新增 `tests/test_kb_health.py` 5 项；相关回归 107 passed；`npm run build` 通过。
  - **全量 pytest 仍会挂**：按文件分批跑，`test_mcp` / `test_answer_engine` / `test_abstain` / `test_report` / `test_user_mode` 需网络或长时间运行会卡；**已用 `git stash` 对照确认与本次改动无关**（无改动时同样 124 超时）。
  - **前端同时完成**（同一 session 前半段）：LLM-Wiki 一实体一页（`softwiki/wiki/subject_pages.py`）、侧栏五组重构、documents/claims/LLM Wiki 分页、徽章完整数字、表格列宽修整、AdminPanel（用户放行 + 审计）。

- **2026-11-19 身份接入 / 权限 / 图谱 / 建库向导**（一次端到端落地）：
  - **权限 fail-closed**：`permissions.py` 未知角色回退 `wiki-study`（原回退 `wiki-admin`）；角色中间件不再读 `X-SoftWiki-Role`；`_load_policy` 的可疑输入改为 log + 明确降级。
  - **降级工作模式**：有效角色 = `min(固有, 会话降级)`；请求级用 `X-SoftWiki-Downgrade` 或 `softwiki_downgrade` cookie；`/api/auth/downgrade` 只能降不能升，降级后 `require_capability`/管理面一并按有效角色判定。
  - **审计**：`softwiki/audit.py`，JSONL 落 `<workspaces root>/.softwiki-audit/audit.log`（`SOFTWIKI_AUDIT_LOG` 可覆盖）；API 记录所有非 GET 请求（含异常），MCP 记录 ingest/index/wiki_build/workspace_set/modules_set；只读不记。
  - **超级用户**：`identity/superuser.py`；`off` 模式即机器本人（有本地行 `local:machine:superuser`）；其他模式默认关闭、仅本机（看 `request.client.host`，**不看** `X-Forwarded-For`）、远程开启强制 TTL、敏感操作二次认证（`SOFTWIKI_REAUTH_TOKEN` 缺省回退 `SOFTWIKI_SUPERUSER_TOKEN`）。
  - **身份源**：`identity/base.py` 统一 `(issuer, subject, 属性)`；`oidc.py` 解析 claims；`wechat.py` 走 code→token→userinfo（微信无组信息，只能 pending 后人工授权）。
  - **本地用户表**：`<workspaces root>/config/users.yaml` + `identity.yaml`；角色**每次请求重算**（改映射不用重新登录）；`is_active=false` 优先于外部组；三态 `pending|lowest|deny` 默认 `pending`。
  - **`kb_scope`**：默认 `*` 通配（新库自动可见）；typo 不阻断但 `/api/admin/users` 返回 `kb_scope_empty`。
  - **知识库注册表**：`kb/registry_state.py` + `config/kbs.yaml`；目录存在但无记录视为已注册（老部署零迁移）；卸载=脱钩，数据保留，可重新注册。
  - **建库向导**：`POST /api/kb/create`（`dry_run` 默认 true）+ `/api/kb/templates` + `/api/kb/registry`；模板 `generic`/`research-report`/`course-qa` 在仓库 `kb-templates/`；WebUI「新建库」面板（zh/en/ja）。
  - **图谱**：新增 `/api/graph/overview`（按度数取 Top N）与 `/api/graph/subgraph`（1–2 跳）；前端重写为 Canvas + 分帧力导向 + 缩放/平移/拖拽/悬停高亮/双击展开。旧实现全图渲染 + `nodes.find` + 80 次 O(n²) 迭代是卡死根因。
  - **测试**：新增 `tests/test_identity.py`(37)、`tests/test_kb_wizard.py`(22)、`tests/test_graph_api.py`(5)；`tests/test_mcp.py` 与 `test_user_mode.py` 改为显式角色/降级（原依赖客户端自报）。全量 **175 passed**；`npm run build` 通过。
  - **易踩坑**：`tests/` 里若把 `WORKSPACES_ROOT` 指到临时目录，用户表会写进去；反之会污染仓库 `data/`（已加入 `.gitignore`，本次测试确实产生过 `data/config/users.yaml`）。
  - **未做**：管理面 Web UI、pending 放行界面、标准 OIDC 授权码交换、多进程下超级用户状态存储；**卸载库按 operator 要求暂不做前端强调**（后端已实现且测试覆盖）。

- **2026-11-20 图谱拖拽崩溃修复**：
  - **根因**：`GraphPanel` 在 `setNodes`/`setView` 更新函数里读 `dragRef.current!.dx`/`panRef.current!.tx`；React 可能在 `pointerup` 之后才执行更新函数，此时 ref 已置空 → `null.dx` 抛错。构建与类型检查都发现不了。
  - **同时修**：布局进度改 ref（悬停不再重启布局）、拖拽改为直接改坐标+松手提交（避免每次 pointermove 重渲染侧栏）、滚轮改原生非被动监听、隐藏未展开按存活节点过滤边、指针离开画布清理拖拽。
  - **验证工具**：新增 `scripts/ui-smoke.mjs`（headless Chrome，需 `npm i puppeteer-core`，用 `PUPPETEER_DIR` 指定安装位置）。覆盖拖拽/缩放/侧栏聚焦/展开/双击/隐藏/重置/搜索 + 建库 dry-run。
  - **实测**：coffee 6108 与 ai 6109 均 `nodeDrag=true`、`pageErrors=[]`、`consoleErrors=[]`、无 error overlay；建库校验与预览正常。
  - 已重建 `softwiki-web:latest` 并 force-recreate 两个 web 容器。

- **2026-11-20 Wiki Portal 404 修复 + 移除 SWAgent 入口**：
  - `/wikiweb` 的路由只在 trial-host 上临时加过，从未进仓库，本次重建镜像后消失 → 404。
  - `web/app/wikiweb/route.ts` 补回；门户内容不进 git，改为**放进各自 workspace**：
    `workspace/<kb>/exports/wikiweb/`（`assets/` + `<kb>/`），compose 按栈挂自己那份，
    `WIKIWEB_ENTRY` 指定入口页。
  - **按库分离顺带修掉越权**：原共用落地页同时列出两个库，6108 可点进 ai-history，绕过 `kb_scope`；
    现在跨库路径 404。实测 6108/6109 各站、嵌套分类页、`assets`、`search-index.json` 均 200，
    浏览器侧 `data-kb` 正确、无对方链接、页内搜索可用、无 pageerror。
  - 旧共用副本改名 `wikiweb.old-20261120/`（20MB，可删）。
  - 侧栏 `SWAgent ↗` 与聊天页头 `Agent ↗` 两个外链入口已删；`Quick / SWAgent` 模式切换保留。
  - **遗留**：门户仍是静态快照，Wiki 更新后不会自动重建 —— 需要生成器（`softwiki wiki site`）。

- **2026-11-17 trial-host 汉化核查**：
  - 中国侧在 trial-host 源码上加了前端 i18n：`web/lib/i18n`（zh/en/ja，默认 zh，311 keys，`localStorage` 持久化，缺 key 回退英文），新增 `LanguageSwitcher`，19 个组件/hook 接入 `useT()`，约 730 行；zh/ja key 与占位符均对齐。
  - 已构建进 `softwiki-web:latest`（`41150a94b441`，11-16 11:08），coffee/ai 两个 Web 容器已运行，SSR 输出中文。
  - **未入库**：目标机不是 git 仓库，唯一备份 `backup-20261116/web-src-bak-20261116-1030.tgz`（246MB，只含 `web/`）。
  - 缺口：`layout.tsx` 的 `lang`/metadata、`lib/api.ts` 与后端错误串、claim status 等数据值、Wiki 正文与 `wikiweb` 静态门户（1,087 页全英文）未汉化；`Expand sidebar` 漏翻；语言按钮在侧边栏收起时不可见。
  - 同批非 i18n 改动：`wikiweb` 静态门户 + `/wikiweb` 路由 + compose 挂载；compose 默认库名改成 `softwiki_armkb`。
  - 详情与拉取命令：`docs/03-operations/deployment-trial.md`「前端汉化（i18n）实测」；**待定是否收编进本仓库**。

- **2026-11-10 双机部署（Chat UX P0）**：
  - build-host（javis, 10.3.9.29）：CI 自动部署 `65555d72da29`，api/web 容器已换新镜像；`/api/agent/events` 经 6108 验证有 `server.connected`。
  - trial-host（bcis1996, 118.193.105.3）：git 被墙，手动 tar 同步 + 重建；coffee（6200/6100/6108）与 ai（6202/6102/6109）全部重建，`swagent-coffee`/`swagent-ai` 重启；两端 SSE 均验证。
  - 修正 trial `.env.ai` 的 `AGENT_WEB_URL` 6111→6112（原来 AI API 指向 coffee agent）。
  - 备份：`/opt/aitools/apps/softwiki/backup-src-20261111-0638.tgz`、`backup-images-20261111-0638.txt`；更新步骤写入 `docs/03-operations/deployment-trial.md`。
  - 未做真实对话 E2E（省 token）；permission/question 卡片、P1 Quick 阶段事件仍未做。

- **2026-11-10 Chat UX P0 落地**：
  - 后端：`GET /api/agent/events`（httpx + 队列 + 15s 心跳；`/global/event` 404 回退 `/event`；按 session 过滤）、`POST /api/agent/prompt`（`prompt_async`）、`GET /api/agent/sessions`、`GET /api/agent/session/{id}/messages`；`httpx` 进 pyproject。
  - 前端：`app/api/agent/events/route.ts` 原始 body 直转；`lib/agent-chat.ts` reducer；`chat/useAgentChat.ts`（rAF 合帧、先开流再发、停止/重试/历史）；`chat/{ToolCard,AgentMessageView}`；ChatPanel SWAgent 分支；ChatMessage 接 remark-gfm。
  - 验证：pytest **95 passed**（新增 `tests/test_agent_stream.py` 9 项）；`npm run build` 通过；假上游 + `next start` 实测 SSE 0.6s/条不缓冲。
  - **未做**：本机无 6200/6111，未做真实 opencode 端到端；permission/question 卡片；P1 Quick 阶段事件；Last-Event-ID。
  - 风险：依赖 opencode 1.19.5 事件字段（`properties.part/info.sessionID`）；若上游版本不同需按 §9 契约调整。

- **2026-11-10 Chat UX 判断 + 设计**：
  - 判断：我们 chat 薄在**数据流一次性**——`/api/agent/ask` 是服务端阻塞轮询（`softwiki/api/server.py:643`），前端只拿到终态；opencoco 则是 `EventSource(/global/event)` 增量渲染 parts。
  - 结论：可做，但只参考 opencoco 的 chat 模型（SSE parts / tool 卡片 / 停止重生成 / 会话列表 / 内联 permission·question），不引入舰队/代理/inbox/skillcell/terminal，不移植代码。
  - 产物：`docs/02-design/chat-ux.md`（🚧 讨论中，含差距表、事件契约、P0/P1/P2 与验收、风险、D1–D6）；已挂 `docs/README.md` 索引与交接。
  - P0 前置：定「会话 → KB」绑定；opencode 事件 schema pin 1.19.5 + 契约测试；SSE 代理放 FastAPI（非浏览器直连）。
  - 附：本 session 的 permission 弹窗实验结论——当前会话跑在 `opencode web --port 4097`（server cwd `/`），项目 `opencode.json` 的 `permission.bash=ask` **未生效**；`build` agent 顶部有 `permission:"*"→allow` 通配规则，故 bash/write 一律不弹窗；`read *.env` 是唯一会 `ask` 的规则。

- **2026-11-03 语料补齐**：
  - 结论：trial-host 的网络是**两层封锁**——DNS 污染（Guardian/Atlantic → `face:b00c` Facebook 段、Wikipedia → `2001::1`）+ TCP 层 RST（用真实 IP + 正确 SNI 仍 `000`）。**改 DNS 救不回**，trial-host 也无 IPv6 / 无代理。
  - 做法：开发机抓正文 → 清洗成 markdown（front matter: title/author/date/url）→ tar 推到 trial-host → `trial_ingest.sh` 节流入库 → `/api/index`。
  - 结果：coffee 185 docs / 6,691 claims；ai-history 160 docs / 9,526 claims；两者均 0 stale wiki，ask 带来源名与引用。
  - 途中修了 4 个会静默毁掉整篇抽取的 bug：`published_at` 为 None 时 strftime 崩溃；事件无日期写 NULL 违反 NOT NULL；失败后不 rollback 导致 status 卡在 `extracting`；varchar(100) 字段未截断导致 `StringDataRightTruncation`。
  - 新增脚本：`scripts/trial_sources.py`、`scripts/trial_fetch.py`、`scripts/trial_ingest.sh`。
  - 仍未做：markdown 无页码（`page_start` 为 None）；`scope_guard` 会判掉约 20 篇企业/预测类稿件；Wiki 覆盖率未重算。

- **做了什么**：确认工作方式（AGENTS.md / progress.md / docs-first / 小步提交）；确认试用边界（单校自部署、答案+报告、手动/自动/关闭三态裁决）；定位并修复 venv 与 MCP 别名问题；落地试用清单；核查 build-host 现有 systemd 部署；落地 Docker Compose + CI 轮询并本地端到端验证；完成 build-host 切流；修复 OpenAI embedding 与 chunk 上限，重建索引并验证 `search`/`ask`；新建 `kb-alpha` 并启动 81 篇 ARM 技术文档入库。
- **关键产物**：
  - `AGENTS.md`（项目宪法）
  - `progress.md`（本文件）
  - `docs/05-roadmap/trial-readiness.md`（10 步验收 + P0/P1 任务）
  - `Dockerfile` / `docker-compose.yml` / `scripts/ci-deploy.sh` / `docs/03-operations/deployment-build.md`
  - `docs/06-archive/session-report-2026-10-23.md`（本轮完整报告）
- **易踩坑**：
  - `venv` 的 editable 安装原本指向 `/home/operator/mydrv/git/softwki`（空壳），导致测试导入错仓库；
  - `tests/__pycache__` 里的旧 `.pyc` 仍带旧路径；
  - 全量 pytest 会挂起，必须先离线 mock；
  - `mcp>=2` 会把 `FastMCP` 改名并破坏 `softwiki.mcp.sse`，必须 `<2.0.0`；
  - OpenAI embedding 单条上限 8192 tokens；旧 `chunk_text` 在无标点长段落上产出过 56k 字符 chunk，必须在 chunker 层限长；
  - OpenAI 账户 TPM 只有 1M；40M 字符语料至少要 45–60 分钟，batch=500+4 并发会 429；必须用 `EMBEDDING_TPM` 限速器；
  - `/api/index` 重建 chunk 会换 ID；向量索引必须先 `reset()`，否则索引指向已删除的 chunk，搜索返回空；
  - `/api/ingest/file` 只建 Document + 后台抽取，不切块/不向量化；必须再调 `/api/index`；
  - `run_extraction_pipeline` 只取前 15k 字符，大手册结构化层不完整；
  - `switch_workspace` 是进程级；容器重启后以 `SOFTWIKI_ACTIVE_WORKSPACE` 为准（已设 kb-alpha）；
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
- **2026-10-25 Wiki Prompt Studio 追加**：
  - 新代码：`softwiki/wiki/interventions.py`、`softwiki/wiki/coverage.py`；`page_generator.py` 支持 intervention/输出目录/hash；API `/api/wiki/preview|apply|interventions|coverage`；UI `WikiPanel` Prompt Studio。
  - 验证：preview 61.8s（canonical hash 不变）；saved topic intervention 生效；apply 35.2s；删除 intervention 后 full rebuild 恢复；UI modal 可见，preview 请求完成（preview 文件生成）。
  - 初始策展地图：`kb-alpha/config/topics.yaml` 29 个主题（IP/协议/技术 group）；当前 4 个 canonical 页面。
  - Claim 覆盖率：**3.4%**（360/10,573 mapped；10,213 unmapped；0 ignored）；top unmapped 为 `inclusive-language`/`export-compliance`/`warranty-disclaimer` 等法务/模板 topic。
  - 已完成：三级分类 + alias-aware 合并页；12 页生成（amba/pq-channel/instruction-set/system/low-power/soc + cortex-m55/cortex-m85/ethos-u55/nic-400/pl031/pck-600）；旧 4 页归档；PL301 no_docs；DMA 空类目。
  - Claim 覆盖率：**15.94%**（1,685/10,573 mapped；1,107 ignored；7,781 unmapped；effective **17.80%**）。top mapped：AMBA 496、SoC 268、System 218、Low Power 200、P/Q 185、Instruction Set 131、PL031 110、U55 29、CM85 19、NIC-400 14。
  - 未完成：index/ingest 自动重建、7,781 unmapped 的 alias/ignore、PL301 文档。
- **2026-10-25 知识系统思想追加**：
  - 新增 `docs/02-design/knowledge-system-philosophy.md`：Claim 事实源、Graph/Timeline/Wiki 投影、重复/冲突/版本/人工裁定、LLM-Wiki 方法论与规模策略。
  - 新增 `docs/05-roadmap/knowledge-system-plan.md`：A–N 工作流、P0/P1/P2、依赖图、风险、迁移、65–100 人天粗估。
  - 当前代码仍无 ClaimEvidence/status/Contradiction/人工裁定；Graph 与 Claim 仍并行抽取；Wiki 手动生成。
- **2026-10-30 Knowledge v2 v0 追加**：
  - 新增 `softwiki/knowledge/{canonical,versioning,conflicts}.py`；`CanonicalClaim` / `ClaimEvidence` / `Contradiction` / `Adjudication` / `WikiArtifactState`。
  - 迁移：`scripts/knowledge_v2_migrate.py`（schema+版本+canonical+evidence+冲突扫描）；`knowledge_v2_rescan.py`（清理首轮过宽冲突）；`knowledge_v2_wiki_states.py`（12 页 stale）。
  - 数据：10,573 raw claims → 9,766 canonical；10,573 evidence；807 merged；当前 0 open conflicts（保守 v0）。
  - UI：Sidebar **Conflicts**；`ConflictsPanel` 支持 accept A/B、keep both、mark error、needs evidence、reopen；Wiki stale banner。
  - AnswerEngine：canonical active/disputed + conflict context + 不静默选边；Graph/Timeline 过滤 active。
  - 备份：build-host `/tmp/kb_alpha_before_knowledge_v2.sql`（116MB）。
  - 追加：12 页已用 canonical claims + 类别模板重建（stale 0）；Graph 6,994/7,211、Timeline 599/639 挂 canonical claim；chunk dedup；近重复 6 对报告。
  - 追加：`wiki_rebuild_tasks` durable queue + API worker（auto enqueue）；`wiki_artifact_versions` + History API/UI；adjudication/scan 后 reproject Graph/Timeline status。
  - 未完成：Graph/Timeline 版本链与 evidence 多对多、NLI/结构 claim、近重复自动合并、Tier 2。
- **可回收**：所有结论已落库。下个 session 读 `AGENTS.md` + `progress.md` + `docs/05-roadmap/agent-web-plan.md` + `docs/04-guides/demo.md` + `docs/04-guides/wiki-prompt-studio.md` 即可接手。
