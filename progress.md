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
  - 核查 javis 部署现状（systemd 三服务 + `make deploy`）。
- **本 session 提交 / 推送（策略 A）**：
  - `eb6f98d` docs(agents): 项目宪法与进度台账
  - `ae067eb` docs(roadmap): 试用就绪清单
  - `e853318` docs(roadmap): SI-1
  - `7645e5e` fix(mcp): 兼容别名
  - `a3d1c9d` feat(mcp): 双传输
  - `fd69c5b` docs(progress): session 交接
  - `6bdb598` fix(config): Optional 导入
  - 已推送 `origin/master`（`f19c296..6bdb598`）。
- **部署现状（javis = 10.3.9.29）**：
  - 机器：x86_64 / Debian 13 / Docker 26.1.5 + Compose 2.26.1 / 62GB RAM / RTX 3090 24GB / 422GB 可用。
  - 现有：systemd 三服务 `softwiki-api`（6200）/ `softwiki-mcp`（6100）/ `softwiki-web`（6108），运行目录 `/opt/aitools/apps/softwiki`；源码 clone `~/mydrv/git/softwiki`，`make deploy` = 前端 build + rsync + systemctl restart。
  - clone 本地有**未推送**的 `84e25ae`（Makefile CI/CD）；其未提交的 `config.py` / `sse.py` 修复已在本仓库落库。
  - 已装 Ollama（11434），模型含 `nomic-embed-text`、`gemma4:26b`、`mistral-small3.1`、`deepseek-r1`。
  - **建议（待确认）**：迁移到 Docker Compose；CI/CD 先用 systemd timer 轮询 `origin/master`（无需 runner），后续可换 Forgejo Actions / registry。

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
- [ ] T12 Docker Compose + TLS + `/health` + CI/CD（timer 轮询 `origin/master`）
- [ ] T13 备份 / 恢复脚本
- [ ] T14 每模板 10 个 golden questions + 验收文档

## Pending issues / Blocker

- [!] **20 篇真实 PDF**：未提供；没有样本无法做抽取质量验收。
- [!] **出站 LLM/embedding 是否允许**：未确认；若学校内网不允许，需要校内模型（vLLM/Ollama），Docker 方案会变。
- [!] **测试基线不可信**：全量 `pytest` 挂起（>120s），疑似真实网络调用；M0 未完成前，任何“通过”都不可信。
- [ ] **数据库选择**：试用版 Postgres 还是 SQLite？（建议 Postgres；SQLite 只适合单用户演示）
- [ ] **OCR 范围**：扫描版 PDF 是否必须支持？决定 T1 工作量。
- [ ] **既有未提交改动**：MCP transport 改造需要单独提交/验证，不要与新工作混在一起。
- [!] **部署方式待确认**：Docker Compose 迁移 vs 保留 systemd；端口/反代；Ollama 是否作为默认 embedding/LLM。

## 下一步（NEXT）

1. **部署方案**：确认 Docker Compose vs 保留 systemd；写 Dockerfile / compose + CI timer（javis）。
2. **T0 收尾**：清 `tests/__pycache__` → 加离线 mock → 修陈旧断言 → 拿到可信的 `pytest` 基线。
3. **T1/T2**：PDF 页码/段落 + Chunk offsets + 迁移脚本；先用生成的测试 PDF 跑通代码路径。
4. 等用户提供 20 篇 PDF 与出站 LLM 结论后，做抽取质量验收。
5. 决定 Postgres/SQLite 与 OCR 范围后，进入 M2（认证/隔离）。

## 本 session 状态记录（handoff）

- **做了什么**：确认工作方式（AGENTS.md / progress.md / docs-first / 小步提交）；确认试用边界（单校自部署、答案+报告、手动/自动/关闭三态裁决）；定位并修复 venv 与 MCP 别名问题；落地试用清单；核查 javis 现有 systemd 部署与 Docker 可行性。
- **关键产物**：
  - `AGENTS.md`（项目宪法）
  - `progress.md`（本文件）
  - `docs/05-roadmap/trial-readiness.md`（10 步验收 + P0/P1 任务）
- **易踩坑**：
  - `venv` 的 editable 安装原本指向 `/home/faye/mydrv/git/softwki`（空壳），导致测试导入错仓库；
  - `tests/__pycache__` 里的旧 `.pyc` 仍带旧路径；
  - 全量 pytest 会挂起，必须先离线 mock；
  - `/api/ask` 会重复检索一次，且 `AskRequest` 丢弃 `mode`/`history`；
  - `scope guard` 没有接进 `AnswerEngine.ask`；
  - workspace 切换是全局 `os.environ`，并发用户会互相覆盖。
- **可回收**：所有结论已落库。下个 session 读 `AGENTS.md` + `progress.md` + `docs/05-roadmap/trial-readiness.md` 即可接手。
