# 技术方案选择总表

> 状态：✅ 已采用 ｜ 🧪 可选（默认关闭/未安装） ｜ 🚫 明确不采用 ｜ ⚠️ 已采用但有已知欠账
> 最后核对：2026-11-25（javis `9fca6c0` + trial pgvector 部署）
>
> 这份文档只回答「我们选了什么、为什么、没选什么」。实现细节见各设计文档，
> 执行状态与待办见根目录 `progress.md`。

---

## 1. 运行时与框架

| 层 | 选择 | 状态 | 理由 | 没选 |
|---|---|---|---|---|
| 后端语言 | Python 3.10+ | ✅ | 生态、LLM/MCP SDK | Go、Node |
| Web 框架 | FastAPI + uvicorn | ✅ | 异步、OpenAPI、与现有代码一致 | Django、Flask |
| ORM | SQLAlchemy 2.x（同步） | ✅ | 一套代码跑 PG/SQLite | async SQLAlchemy、raw SQL |
| 迁移 | 启动时幂等 DDL + 一次性脚本，**无 Alembic** | ⚠️ | 简单；多实例并发 DDL 有竞争风险 | Alembic、Flyway |
| CLI | Click | ✅ | 现有 reextract/index 命令 | Typer |
| 前端 | Next.js 16（App Router） | ✅ | SSR + rewrite 反代、已上线 | Vite SPA |
| 对外接口 | MCP（FastMCP：stdio / SSE / HTTP） | ✅ | 统一能力边界，agent 直接接 | 自定义 RPC |

## 2. 存储

| 数据 | 选择 | 状态 | 理由 | 没选 |
|---|---|---|---|---|
| 结构化（文档/chunk/claim/图/任务/事件） | **PostgreSQL，每 KB 一个 database** | ✅ | 隔离、事务、备份简单 | 单库多 schema；SQLite 仅单机回退 |
| 向量 | **PostgreSQL + pgvector**（`chunk_embeddings` + HNSW） | ✅ 2026-11-25 | 不再全量载入内存；增量 upsert；删 chunk 级联 | 文件 npz（保留回退）、FAISS、Qdrant、Milvus |
| 稀疏检索 | **BM25Okapi + pickle**，自研中英分词 | ✅ | 中文分词可控；RRF 分数已标定 | ES/OpenSearch、PG 全文（需中文分词扩展） |
| 图 | **关系表** `entities` / `relationships` / `events` | ✅ | 万级边、1–3 跳、与 claim 同事务 | Neo4j、JanusGraph |
| 身份/用户 | 独立 auth（SQLite 默认，可配 PG） | 🧪 | 与业务数据解耦；auth 关闭时不创建 | 塞进业务库 |
| 审计 | JSONL 文件 | ✅ | 追加写、易采集 | 审计表、ELK |
| 任务队列 | `wiki_rebuild_tasks` durable 表 + worker | ✅ | 无需额外中间件 | Celery、Redis Queue |
| LightRAG 存储 | 未启用 | 🧪 | 见 §4 | — |

### 2.1 向量后端细节

- 开关：`SOFTWIKI_VECTOR_BACKEND=pg|file`（默认 `file`，可回退；两环境均已切 `pg`）。
- 表：`chunk_embeddings(chunk_id FK ON DELETE CASCADE, model, dim, embedding vector(1536))`，HNSW `m=16, ef_construction=64`。
- 查询必须：`SET LOCAL hnsw.ef_search=max(40,k*4)` + `SET LOCAL enable_seqscan=off`。
- 迁移：`scripts/migrate_vectors_to_pg.py`（过滤孤儿 → 分批 upsert → 建索引 → recall 校验）。
- 实测：armkb 39,870 向量、recall@50 99.7%、查询 4.7ms；trial 两库 100%、~4ms。
- 细节：`docs/03-operations/storage.md`。

## 3. 抽取与知识层

| 选择 | 状态 | 理由 | 没选 |
|---|---|---|---|
| LLM 三条抽取管线（claim / graph / timeline）并行 | ✅ | 各自可关、可独立演进 | 单 mega-prompt |
| 按窗口抽取（12k 字符，默认 6 窗口） | ✅ | 长文档不爆 context | 整篇塞入 |
| 窗口内并发（默认 2 窗口 × 3 抽取器），DB 写串行 | ✅ | 吞吐与 session 安全 | 全并发 |
| Graph prompt：ARM 领域 taxonomy、aliases、受控关系词、confidence、证据短语、端点校验 | ✅ | 图质量 | 通用 prompt |
| 抽取失败：3 次退避重试 → 仍失败跳过该窗口，不写启发式 | ✅ | 宁缺勿假 | 大写词兜底 |
| Claim canonicalization：确定性 key | ✅ | 可复现、可合并 | LLM 聚类 |
| 结构化 claim（subject/predicate/object） | 🧪 按需 | 冲突检测需要 | 全量强制 |
| 冲突：规则 v0 + NLI/LLM judge | ✅ | 保守、可人工裁定 | 全自动判定 |
| 人工裁定（Adjudication） | ✅ | 冲突必须有人拍板 | 自动选边 |

## 4. 图与 GraphRAG

| 选择 | 状态 | 理由 | 没选 |
|---|---|---|---|
| 自研 GraphExtractor + 关系表 + 实体链接 1–2 跳 | ✅ | 可控、可解释、和 claim/wiki 同库 | 直接用 LightRAG/Neo4j |
| 实体归一：normalized_name + 别名表 + merged_into | ✅ | 同名合并可追溯 | 模糊合并 |
| 人工别名配置 `config/entity_aliases.yaml` | ✅ | 跨拼写（Helium↔MVE）可控 | 自动全量合并 |
| 边权重 `weight` = distinct 文档数 | ✅ | 跨文档佐证强度 | 只用 confidence |
| **LightRAG** | 🧪 **未安装、未启用** | optional extra；会引入第二事实源、抽取翻倍 | 作为主图 |
| **Neo4j / 图数据库** | 🚫 | 1 万级边关系表足够 | — |
| 图作为「路由层」，claim 才是事实 | ✅ | 项目原则 | 图直接产事实 |

### 4.1 为什么不用 LightRAG

LightRAG 是「一套 GraphRAG 实现」，不是图本身。我们已经用自研抽取 + 关系表 + CGW 检索
实现了它提供的能力，而它带来的是：第二套图（可能对不上）、每篇再抽一遍（+100–200%）、
UI/claim/wiki 都不消费它。触发重新评估的条件：多跳问答评测显示我们明显不足、
需要社区/主题摘要类能力。详见 `docs/02-design/graph-claim-wiki.md`、`docs/02-design/graph-rag.md`。

## 5. 检索与回答

| 选择 | 状态 | 理由 | 没选 |
|---|---|---|---|
| 向量 + BM25 → **RRF** 融合 → MMR → chunk 去重 | ✅ | 简单稳定 | 学习型 reranker |
| 实体链接：确定性（归一化、ASCII 边界、中文 n-gram、别名、度数） | ✅ | 零 LLM 成本、可解释、p50 ~62ms | 向量召回实体 |
| CGW：Graph 路由 → Claim 挂载 → Wiki 叙事 → RAG 原文 | ✅ | 三者取长补短 | 纯 GraphRAG / 纯 RAG |
| 权威层级：**Claim > RAG 原文 > Graph 路由 > Wiki 叙事** | ✅ | 冲突时不静默 | 三者平权 |
| 只用 active/disputed，冲突显式呈现 | ✅ | 知识纪律 | 自动选边 |
| 引用：claim 页码 + 边出处 + citation_check | ✅ | 可追溯 | 只给文档名 |
| 弃权 / scope guard | ✅ | 越界不硬答 | 一律作答 |

## 6. LLM-Wiki

| 选择 | 状态 | 理由 |
|---|---|---|
| 一实体一页，固定 25 条上限，超限拆页不截断 | ✅ | 避免单页退化 |
| 三态界面 + 自动增量重建（worker 轮询） | ✅ | 不阻塞入库 |
| `wiki_subjects.yaml`：ignore / locked | ✅ | 人工干预 |
| Prompt Studio（global/group/topic + preview/apply + hash） | ✅ | 提示词可对比、可回滚 |
| stale 跳过；拆页用 `read_subject_page` 拼接 | ✅ | 不拿旧叙事覆盖新事实 |

## 7. 多 KB 与隔离

| 选择 | 状态 | 理由 |
|---|---|---|
| 请求级 workspace（ContextVar，不写 `os.environ`） | ✅ | 并发不串库 |
| 一个 MCP 端口服务多库：`kb_list/kb_describe` + `kb` 参数 | ✅ | agent 自己路由 |
| 每栈私有 workspace 根 `workspace/stacks/<stack>/<kb>` | ✅ | 文件级隔离 |
| engine 按 DB URL 缓存（LRU 32） | ✅ | 多库不反复建连 |
| 加库 = 建目录 + `CREATE DATABASE` | ✅ | 零代码扩容 |

## 8. 身份与权限

| 选择 | 状态 | 理由 |
|---|---|---|
| 三模式：off / proxy / OIDC | ✅ | 单机、反代、正规 IdP |
| 只信任受信反代 header（CIDR 白名单） | ✅ | 信任边界在代码内 |
| 角色 wiki-study/work/manage/admin + `kb_scope` | ✅ | 最小能力集 |
| 降级工作模式（只降不升）、审计、超级用户默认关闭 | ✅ | 团队试用安全 |
| 内置 admin：scrypt + 限速 + 无默认密码 | ✅ | 反代故障时仍能登录 |
| 文档级 ACL | 🚫 | 当前 KB 级足够 |

## 9. Agent 与前端

| 选择 | 状态 | 理由 |
|---|---|---|
| opencode 作为 agent engine（pin 1.19.5） | ✅ | 不自研 agent loop |
| WebUI Quick / SWAgent 双模式，chat 走 SSE | ✅ | 增量渲染、可停止/重试 |
| agent 工具级权限：所有 profile deny bash/edit/write；study 只读、work propose、manage ingest/index/build | ✅ | 写操作按角色收敛 |
| 前端 i18n（zh/en/ja，默认 zh） | ✅ | trial 客户要求 |
| Graph Studio `/graph-studio` | ✅ | 演示与排查 |
| 侧栏分组 + 角色驱动可见性 | ✅ | 权限与导航一致 |

## 10. 部署与运维

| 选择 | 状态 | 理由 | 没选 |
|---|---|---|---|
| Docker Compose（api / mcp / web / postgres） | ✅ | 单校自部署 | K8s |
| build-host：git push → CI timer 构建 + 健康检查 + 自动回滚 | ✅ | 源码/镜像/仓库一致 | 手工部署 |
| trial-host：**手工同步**（tar + `Dockerfile.api-fast` + 离线 web build） | ⚠️ | 目标机到 Forgejo/Docker Hub/npm 均不通；带宽 ~87KB/s | 在 trial 跑 CI |
| postgres 镜像：`POSTGRES_IMAGE` 可覆盖（javis/trial 用 `pgvector/pgvector:pg16`） | ✅ | 同 major PGDATA 直接复用 | 自建镜像 |
| trial 拉镜像：`docker.1ms.run` 镜像源 + `docker tag` | ✅ | Docker Hub 不可达 | 直连 Docker Hub |
| 镜像 tag = commit sha，旧镜像留 `pre-*` | ✅ | 可回滚 | latest 漂移 |
| LLM 网关：oneroute + `deepseek-v4.1-flash`；key 只在 `.env` | ✅ | 成本/可达性 | 各家直连、明文 key |
| 备份：`pg_dump` + workspace tar | ✅ | 可恢复 | 只备份代码 |

## 11. 评测与可观测

| 选择 | 状态 | 理由 |
|---|---|---|
| `graph_acceptance.py` + 24 题 ARM golden set（实体命中 / 术语覆盖 / p50-p95） | ✅ | 能量化，不烧答案 token |
| `/api/knowledge/metrics`、acceptance 11/11 | ✅ | 回归与运营 |
| 审计 JSONL（非 GET 请求 + MCP 写操作） | ✅ | 合规与排查 |
| 咖啡 / AI-history 的评测集 | ⚠️ 未建 | 只有 ARM 语料有 golden set |

## 12. 明确不采用 / 暂缓

| 项 | 状态 | 原因 |
|---|---|---|
| Neo4j / 专用图数据库 | 🚫 | 万级边用 SQL 足够 |
| LightRAG 作为主图 | 🚫（可选未装） | 第二事实源、抽取翻倍、无 UI 消费 |
| 文档级 ACL | 🚫 | KB 级 `kb_scope` 足够 |
| OCR | 🚫（暂缓） | 扫描版 PDF 不支持 |
| 自研 agent 框架 | 🚫 | 外部工具自带 loop |
| Alembic | 🚫（暂缓） | 启动幂等 DDL 够用，多实例风险可接受 |
| pgvector 迁移 | ✅ 已完成 | 见 §2.1 |

## 13. 已知欠账（有决策但没做完）

| 项 | 风险 | 计划 |
|---|---|---|
| ~~`SOFTWIKI_DISABLE_LIGHTRAG` 只拦查询~~ | 已修（2026-11-25）：入库与查询同开关 | — |
| trial 无 CI | 每次手工同步，易漂移 | `scripts/deploy-trial.sh` 已就绪；公网 git 反代可达，CI 可选 |
| trial 仍是手工 web i18n（不在 git） | 前端改动无法追溯 | 收编进仓库 |
| 咖啡/AI 库没有 golden set | 回答质量无法量化 | 各建 20 题 |
| BM25 仍是 pickle | 百万级/多写者会受限 | 观察，非当前瓶颈 |
| 平均边权重 1.12 | 跨文档互证少 | 图质量迭代 |
| 无 Alembic | 多实例同时启动 DDL 竞争 | 多实例部署前补 |
