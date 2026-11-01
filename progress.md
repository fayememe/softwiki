# progress.md — softwiki 进度台账 ★

> **从此刻起，所有推进基于本文件。随时更新。** 下个 session 只读 `AGENTS.md` + 本文件 + `docs/README.md` 即可接手。
> 图例：`[x]` 完成 ｜ `[ ]` 待办 ｜ `[~]` 进行中 ｜ `[!]` 阻塞

## 当前状态（快照）

- **项目**：softwiki = 多策略研究智能引擎（RAG / GraphRAG / LLM-Wiki / ClaimDB / Timeline）。
- **当前阶段**：**试用就绪（Trial Readiness）**，目标 = 单校、单实例、自部署、试用评估。
- **SWAgent（2026-10-24）**：L1/L2 已上线。WebUI **Quick / SWAgent** 双模式；opencode engine pin **1.19.5**（内置路径 `/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode`）宿主 `:6111`；API `:6200/api/agent/*`；systemd `softwiki-agent-web`；模型 `gpt-4.1-mini`；acceptance **11/11**；浏览器 Agent 模式已验证。
- **知识系统思想（2026-10-25）**：已落 `docs/02-design/knowledge-system-philosophy.md`（Claim 为事实源；Graph/Timeline/Wiki 为投影；重复/冲突/版本/人工裁定；LLM-Wiki 方法论与规模策略）。实现计划/难度：`docs/05-roadmap/knowledge-system-plan.md`。
- **Knowledge v2 v0（2026-10-30）**：schema v2 + canonical claim 9,766 / evidence 10,573；Conflicts API/UI；Adjudication API/UI；AnswerEngine 只读 active/disputed；12 个 Wiki 页面已用 canonical claims 重建，stale 0；Graph 6,994/7,211、Timeline 599/639 已挂 canonical claim；Wiki rebuild worker + artifact history；structured claim fields + NLI judge（1 个真实冲突，2 claims disputed）；近重复候选 6 对；备份 `/tmp/armkb_before_knowledge_v2.sql`（116MB）。
- **Wiki Prompt Studio + 三级分类（2026-10-25）**：提示词作为可选 intervention 层；Preview/Apply/保存；左侧改为 **IP 产品 / 协议 / 技术** 三级（IP 子类 CPU/NPU/AMBA/DMA/Other；协议 AMBA/PQ/指令集；技术 System/Low Power/SoC）；合并页 alias-aware；`GET /api/wiki/coverage`。当前 claim 覆盖率 **15.94%**（1,685/10,573；ignored 1,107；effective 17.80%）。**12 个策展页面已生成**；旧 4 页已归档。
- **范围**：见 `docs/05-roadmap/trial-readiness.md`；2 个深模板（研究报告 / 课程问答），wiki 试用阶段只读。
- **Demo/销售（2026-10-31）**：`docs/04-guides/demo-plan.md`（15/30 分钟脚本、失败预案）；`docs/04-guides/sales-training.md`（话术、异议、边界）。
- **角色/权限（2026-10-31）**：`docs/02-design/roles-permissions.md`；4 角色 capability mapping；Web role cookie、MCP `X-SoftWiki-Role`、`configs/permissions.yaml` 可改；team trial `wiki-work` 已开放 ingest/index（Hermes）；document delete canonical cleanup；**MCP role header 实测**（study 拒绝 ingest，work 放行）；无效 base64 已拒绝。
- **远程**：`ssh://git@10.3.9.19:2222/faye/softwiki.git`（branch `master`）。
- **157 team trial（2026-11-01）**：`117.133.38.157`，faye，`/opt/aitools/apps/softwiki`；Web `6108`、MCP `6100`、SWA `6111`、API 仅 `127.0.0.1:6200`；空 `team` workspace / `softwiki_team`，**未部署 armkb**；opencode 1.19.5；DeepSeek；BM25 fallback（无 OpenAI/Gemini 出站）；Hermes Agent + WebUI `9119`（gateway 仅本机 `8642`，MCP `softwiki` 角色 `wiki-work`，实测 16 tools / 0 docs）；详见 `docs/03-operations/deployment-157.md`。
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
- **157 部署注意**：目标机无 CI timer；需手动同步/rebuild；Web/SWA/MCP 公网无 auth，必须安全组限制；embedding 不可达，当前 BM25 fallback。
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

## Pending issues / Blocker

- [x] **真实 PDF**：已提供 81 篇 ARM 技术文档。
- [~] **出站 LLM/embedding**：当前用 OpenAI + DeepSeek；学校内网是否允许出站仍未确认。
- [x] **测试基线**：84 passed（离线；含 knowledge v2 / NLI / citation / permissions / cleanup）。
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
- [ ] **TLS/反代**：javis 无 Caddy/Nginx；试用先用 HTTP。
- [x] **认证/权限**：demo 阶段明确不做（代码保留，默认关闭）。

## 下一步（NEXT）

1. **P1 收尾**：Graph/Timeline 版本继承；evidence 多对多映射；投影重算。
2. **P2 冲突召回**：structured claim 全量/按需；NLI 定时；评测集；人工队列。
3. **Claim 覆盖率**：继续用 alias/新 canonical 收编 7,781 unmapped；当前 15.94%，effective 17.80%。
4. **Prompt 调优**：用 `docs/04-guides/wiki-prompt-studio.md` 的 IP/协议/技术范例，先 preview 再 apply。
5. **Demo**：按 `docs/04-guides/demo.md` 跑 Quick + Agent + Wiki Prompt Studio；acceptance 11/11。
6. **P2**：近重复文档、NLI 冲突、自动 family/revision。

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
- **2026-10-25 Wiki Prompt Studio 追加**：
  - 新代码：`softwiki/wiki/interventions.py`、`softwiki/wiki/coverage.py`；`page_generator.py` 支持 intervention/输出目录/hash；API `/api/wiki/preview|apply|interventions|coverage`；UI `WikiPanel` Prompt Studio。
  - 验证：preview 61.8s（canonical hash 不变）；saved topic intervention 生效；apply 35.2s；删除 intervention 后 full rebuild 恢复；UI modal 可见，preview 请求完成（preview 文件生成）。
  - 初始策展地图：`armkb/config/topics.yaml` 29 个主题（IP/协议/技术 group）；当前 4 个 canonical 页面。
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
  - 备份：javis `/tmp/armkb_before_knowledge_v2.sql`（116MB）。
  - 追加：12 页已用 canonical claims + 类别模板重建（stale 0）；Graph 6,994/7,211、Timeline 599/639 挂 canonical claim；chunk dedup；近重复 6 对报告。
  - 追加：`wiki_rebuild_tasks` durable queue + API worker（auto enqueue）；`wiki_artifact_versions` + History API/UI；adjudication/scan 后 reproject Graph/Timeline status。
  - 未完成：Graph/Timeline 版本链与 evidence 多对多、NLI/结构 claim、近重复自动合并、Tier 2。
- **可回收**：所有结论已落库。下个 session 读 `AGENTS.md` + `progress.md` + `docs/05-roadmap/agent-web-plan.md` + `docs/04-guides/demo.md` + `docs/04-guides/wiki-prompt-studio.md` 即可接手。
