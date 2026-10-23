# progress.md — softwiki 进度台账 ★

> **从此刻起，所有推进基于本文件。随时更新。** 下个 session 只读 `AGENTS.md` + 本文件 + `docs/README.md` 即可接手。
> 图例：`[x]` 完成 ｜ `[ ]` 待办 ｜ `[~]` 进行中 ｜ `[!]` 阻塞

## 当前状态（快照）

- **项目**：softwiki = 多策略研究智能引擎（RAG / GraphRAG / LLM-Wiki / ClaimDB / Timeline）。
- **当前阶段**：**试用就绪（Trial Readiness）**，目标 = 单校、单实例、自部署、试用评估。
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
  - 切流完成：Docker 接管 6200/6100/6108，旧 systemd 已 stop + disable；CI timer 已安装并验证。
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
  - 已推送 `origin/master`（`f19c296..394e858`）。
- **部署现状（javis = 10.3.9.29）**：
  - 机器：x86_64 / Debian 13 / Docker 26.1.5 + Compose 2.26.1 / 62GB RAM / RTX 3090 24GB / 422GB 可用。
  - **当前**：Docker Compose 接管 `6200`（API）/ `6100`（MCP）/ `6108`（Web）；旧 systemd 已 stop + disable；CI timer 每 3 分钟轮询（已手动验证 `up to date`）。
  - 数据：`workspace/` bind mount；embedding 用 OpenAI 1536 维；索引 4196 chunks；`search` 与 `ask` 已验证。
  - 抽取：`cheap_extraction` / `wiki_compilation` 已切 DeepSeek（Google 402）；`claims=0` / `events=0` 仍待重新抽取或新文档。
  - 旧 clone `~/mydrv/git/softwiki` 的 `84e25ae`（Makefile CI/CD）未推送，但已被 Docker CI 取代。
  - Ollama 仍可用（`nomic-embed-text` 等），但当前不用于 embedding。

## 研发计划（checklist）

### M0 — 基线（试用前置）
- [x] 修正 venv editable 指向本仓库
- [x] 补 `softwiki_search` / `softwiki_ask` 别名
- [ ] 清理 `tests/__pycache__`（旧 `.pyc` 的 `co_filename` 仍指向 `softwki`）
- [ ] 测试离线化：embedding / LLM / LightRAG 不发真实网络请求
- [ ] 修 `tests/test_answer_engine.py` 的陈旧断言（`Direct Answer` / `Evidence Summary` 已不存在）
- [ ] `pytest tests -q` 无网络下 60 秒内完成，0 error

### M1 — 能信（P0）
- [ ] T1 PDF 页码/段落：`pdf_loader` 返回 `pages[{page_no,text}]`，空页显式记录
- [ ] T2 Chunk 元数据：`page_start/page_end/char_start/char_end` + 幂等迁移脚本
- [ ] T3 统一 chunk 创建（现在 5 处重复）
- [ ] T4 RAG 引用带页码/span
- [ ] T5 全层引用（claim / graph / timeline / wiki）
- [ ] T6 弃权 + 问答时 scope 强制

### M2 — 能隔离（P0）
- [ ] T7 认证（本地账号 + 会话；API/MCP 拒绝匿名）
- [ ] T8 按用户 workspace（去掉全局 `WORKSPACE_DIR` 切换）
- [ ] T9 库级 ACL（owner / editor / viewer）

### M3 — 能交付（P1）
- [ ] T10 模板系统 + `research-report` / `course-qa`
- [ ] T11 报告异步 + `report.md` + `manifest.json`
- [x] T12 Docker Compose + CI/CD（已切流 6200/6100/6108；TLS/反代未做）
- [ ] T13 备份 / 恢复脚本
- [ ] T14 每模板 10 个 golden questions + 验收文档

## Pending issues / Blocker

- [!] **20 篇真实 PDF**：未提供；没有样本无法做抽取质量验收。
- [!] **出站 LLM/embedding 是否允许**：未确认；若学校内网不允许，需要校内模型（vLLM/Ollama），Docker 方案会变。
- [!] **测试基线不可信**：全量 `pytest` 挂起（>120s），疑似真实网络调用；M0 未完成前，任何“通过”都不可信。
- [ ] **数据库选择**：试用版 Postgres 还是 SQLite？（建议 Postgres；SQLite 只适合单用户演示）
- [ ] **OCR 范围**：扫描版 PDF 是否必须支持？决定 T1 工作量。
- [x] javis deploy key 已加入 Forgejo（`git ls-remote` 通过）。
- [x] **embedding 已修复**：OpenAI `text-embedding-3-small`（1536 维），分批 + 独立凭据；索引重建为 4196 chunks；`search` / `ask` 已验证。
- [x] **javis 并行栈验收 + 切流 + CI timer**：Docker 接管 `6200`/`6100`/`6108`，旧 systemd 已 stop + disable，timer 已验证 `up to date`。
- [!] **claims=0 / events=0**：抽取已切 DeepSeek，但历史 820 篇未重新抽取；新文档会正常抽取。
- [!] **密钥明文**：`model_profiles.yaml` 仍有明文 DeepSeek key；建议移到 `.env` / secret store，并轮换聊天中暴露的 OpenAI key。
- [ ] **TLS/反代**：javis 目前没有 Caddy/Nginx/Traefik；试用先用 HTTP 端口。

## 下一步（NEXT）

1. **抽取补齐**：用 DeepSeek 重新抽取 lsl-kb，或只对新语料抽取，让 claims/events 有数据。
2. **T0 收尾**：清 `tests/__pycache__` → 加离线 mock → 修陈旧断言 → 拿到可信的 `pytest` 基线。
3. **T1/T2**：PDF 页码/段落 + Chunk offsets + 迁移脚本；先用生成的测试 PDF 跑通代码路径。
4. 等用户提供 20 篇 PDF 与出站 LLM 结论后，做抽取质量验收。
5. **TLS/反代**：试用后加 Caddy，收口 6108/6200。
6. 决定 Postgres/SQLite 与 OCR 范围后，进入 M2（认证/隔离）。

## 本 session 状态记录（handoff）

- **做了什么**：确认工作方式（AGENTS.md / progress.md / docs-first / 小步提交）；确认试用边界（单校自部署、答案+报告、手动/自动/关闭三态裁决）；定位并修复 venv 与 MCP 别名问题；落地试用清单；核查 javis 现有 systemd 部署；落地 Docker Compose + CI 轮询并本地端到端验证；完成 javis 切流；修复 OpenAI embedding 与 chunk 上限，重建索引并验证 `search`/`ask`。
- **关键产物**：
  - `AGENTS.md`（项目宪法）
  - `progress.md`（本文件）
  - `docs/05-roadmap/trial-readiness.md`（10 步验收 + P0/P1 任务）
  - `Dockerfile` / `docker-compose.yml` / `scripts/ci-deploy.sh` / `docs/03-operations/deployment-javis.md`
- **易踩坑**：
  - `venv` 的 editable 安装原本指向 `/home/faye/mydrv/git/softwki`（空壳），导致测试导入错仓库；
  - `tests/__pycache__` 里的旧 `.pyc` 仍带旧路径；
  - 全量 pytest 会挂起，必须先离线 mock；
  - `mcp>=2` 会把 `FastMCP` 改名并破坏 `softwiki.mcp.sse`，必须 `<2.0.0`；
  - OpenAI embedding 单条上限 8192 tokens；旧 `chunk_text` 在无标点长段落上产出过 56k 字符 chunk，必须在 chunker 层限长；
  - Next.js 在 Docker 内反代要 `API_INTERNAL_URL=http://api:6200`，不能用 `127.0.0.1`；
  - `docker compose config` 会把 `.env` 里的真实密钥渲染出来，不要贴日志；
  - `/api/ask` 会重复检索一次，且 `AskRequest` 丢弃 `mode`/`history`；
  - `scope guard` 没有接进 `AnswerEngine.ask`；
  - workspace 切换是全局 `os.environ`，并发用户会互相覆盖。
- **可回收**：所有结论已落库。下个 session 读 `AGENTS.md` + `progress.md` + `docs/05-roadmap/trial-readiness.md` 即可接手。
