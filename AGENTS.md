# AGENTS.md — softwiki

> 本文件是本仓库的 **项目宪法（constitution）**。任何 agent / 协作者在动手前必须先读它，再读 `progress.md` 与 `docs/README.md`。
> 若本文件与 `docs/` 下文档冲突，以已标记为 **✅ frozen** 的设计文档为准，并回填本文件。
>
> 远程仓库：`ssh://git@git.example.internal:2222/operator/softwiki.git`（homelab Forgejo，**private**）。

---

## 0. 第一原则：会话是一次性的，文档是持久的 ★

> 这是本仓库最高优先级的工作纪律。**每次 session 都默认「随时可能中断、且不会再继续」**。

### 0.1 结论必须边走边写

- 每一次 agent chat session 都**随时可能中断、且不会再继续**。只存在于对话里的结论 = 丢失。
- 每完成一个决策 / 发现 / 讨论，**立刻**更新对应文档，不要攒到最后。
- **默认下一个 session 对本对话一无所知**——它只能读到本文件、`progress.md` 和 `docs/`。据此保证文档自洽、可独立接手。

### 0.2 `progress.md` 是推进的唯一基准 ★

- **从此刻起，所有推进以根目录 `progress.md` 为准**，随时更新。
- 内容固定五段：**当前状态** / **研发计划（checklist）** / **pending issues / blocker** / **NEXT** / **本 session 交接**。
- 下个 session 只读 `AGENTS.md` + `progress.md` + `docs/README.md` 即可接手。

### 0.3 结束 session 前的 checklist

1. 新决策已进对应 `docs/` 文档（含决策记录）；
2. 开放问题 / 待办已写进文档；
3. `docs/README.md` 的「当前状态 / 交接」是最新的；
4. `progress.md` 的 checklist / pending / NEXT / 交接 是最新的；
5. 记清 session 状态后，即可回收 session。

### 0.4 文档先行

- **`docs/` 是权威来源**。代码是文档的实现，不是反过来。改了行为要同步改文档。
- 先改 `docs/` → 评审通过 → 再落代码。

### 0.5 Chat 规范

- **chat 不是存储**：聊天里说过的结论，如果没有进仓库，就当没发生。
- 用中文回复（除非用户明确要求其他语言）；简洁、证据优先。
- 不吹捧、不状态表演；直接说结论、依据、风险。
- 假设、未决问题、不确定性要显式写出来，不要静默猜测。
- **没有命令 / 测试 / 代码证据，不宣称「完成」**。
- 破坏性操作（`force-push`、改历史、删分支/仓库、drop 数据库、删除用户数据）必须先问。
- 任何真实 API key / token / 密码 / 个人数据**绝不写进文件或提交**，走 `.env`（已 gitignore）。

---

## 1. 项目是什么

**softwiki = 多策略研究智能引擎**：把 RAG、GraphRAG、LLM-Wiki（Karpathy 架构）统一到一个 MCP 驱动的知识平台里，面向深度研究工作流和隔离的知识库。

- 五层知识：RAG（dense + BM25 + RRF）/ ClaimDB / Knowledge Graph / Timeline / LLM-Wiki；
- 多入口：CLI、Shell TUI、MCP（stdio / SSE / Streamable HTTP）、WebUI、REST API；
- 工作区隔离：每个知识库独立（`WORKSPACE_DIR`）；
- 当前阶段目标：**单校、单实例、自部署、试用评估**，详见 `docs/05-roadmap/trial-readiness.md`。

---

## 2. 当前状态

> ★ **进度台账见根目录 `progress.md`**。所有推进以它为准。

| 阶段 | 状态 |
|---|---|
| Phase 1 核心引擎 | ✅ 完成 |
| Phase 2 Graph + WebUI | ✅ 基本完成（图像系统未做） |
| Phase 3/4/6 远程、权限、部署 | ☐ 未开始（试用版前置） |
| 试用就绪（Trial Readiness） | 🚧 进行中（M0 基线） |

> **纪律**：试用版范围以 `docs/05-roadmap/trial-readiness.md` 为准；不在清单内的大功能，先讨论再动手。

---

## 3. 目录约定

```
softwiki/
├── AGENTS.md              # 本文件，项目宪法
├── progress.md            # ★ 进度台账，推进的唯一基准
├── docs/                  # ★ 设计文档 = 概念与路线的唯一事实来源
│   ├── README.md          # 索引 + 当前状态/交接
│   ├── 01-architecture/
│   ├── 02-design/
│   ├── 03-operations/
│   ├── 04-guides/
│   ├── 05-roadmap/        # status.md（长期路线）+ trial-readiness.md（试用清单）
│   └── 06-archive/        # work-log.md（历史决策）
├── softwiki/              # 源码（Python 包）
├── tests/                 # 测试
├── scripts/               # 开发/运维脚本
├── web/                   # Next.js WebUI
├── workspace/             # 用户数据（gitignored）
└── output/                # 运行产物（gitignored）
```

**`docs/` 是权威来源**。新增设计文档请更新 `docs/README.md` 的索引。

---

## 4. 技术栈

- **语言**：Python 3.10+；
- **后端**：FastAPI + uvicorn；SQLAlchemy（SQLite / PostgreSQL）；
- **检索**：BM25 + 向量（RRF 融合）；LightRAG（可选）；
- **前端**：Next.js 16（`web/`）；
- **接口**：Click CLI、MCP（stdio / SSE / Streamable HTTP）、REST；
- **部署目标**：Docker Compose（单校自部署，见 `trial-readiness.md`）。

---

## 5. 编码与协作规范

### 5.1 硬约束

- **禁止** 用 `as any` / `@ts-ignore` / `# type: ignore` 等抑制类型/错误检查。
- **禁止** 空 `except` / 静默吞异常（至少 log + 明确降级行为）。
- **禁止** 提交 `workspace/`、`output/`、`.env`、`venv/`、`.softwiki_runtime/`。
- **禁止** 在未确认的情况下改数据库结构或删除用户数据。
- 破坏性 git 操作（`force-push`、改历史、删分支/仓库）需**明确要求**后才可执行。

### 5.2 文档规范

- `docs/` 是唯一事实来源；代码实现文档，不是反过来。
- 每份设计文档标注状态：`🚧 讨论中` / `✅ frozen` / `⏳ 待写`。
- 关键决策写进对应文档的「决策记录」，不要只留在 chat。
- 行为变化必须同步更新文档；文档与代码不一致时，先修文档再修代码（除非是紧急 bugfix，事后补文档）。
- `docs/README.md` 维护「当前状态 / 交接」快照。

### 5.3 Git 规范

- **小步提交**：一个逻辑单元一次提交，不要把无关改动混在一起。
- 提交信息格式：`<type>(<scope>): <做了什么>`，正文说明**为什么**；中文正文可用。
  - 常用 type：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`。
  - 例：`feat(ingest): PDF 页码与段落偏移`。
- 提交前必须看 `git status` / `git diff`，只 stage 本次意图内的文件；**禁止 `git add -A` 盲提**。
- 提交时机：完成一个逻辑单元后由 agent 自动提交（不下推到 session 结束）。
- 推送时机：每个里程碑或 session 结束前 push 到 `origin`；中途可按需 push。
- **授权（2026-10-23）**：operator 已确认策略 A —— agent 自动提交（逻辑单元）+ 里程碑 / session 结束自动 push；提交前仍须看 `git status` / `git diff`。
- 推送前确认没有密钥 / 个人数据 / 运行产物；推送失败要记录到 `progress.md` 的 blocker。
- 破坏性操作仍需明确要求（见 §5.1）。

### 5.4 Progress 规范

- `progress.md` 固定五段：**当前状态** / **研发计划（checklist）** / **pending issues / blocker** / **NEXT** / **本 session 交接**。
- 图例：`[x]` 完成 ｜ `[ ]` 待办 ｜ `[~]` 进行中 ｜ `[!]` 阻塞。
- 每完成一个里程碑、每次 session 结束前，必须更新。
- 交接要写清：做了什么、关键产物、易踩坑、哪些可以回收。

---

## 6. 参考

- 项目说明：`README.md`
- 文档索引：`docs/README.md`
- 长期路线：`docs/05-roadmap/status.md`
- 试用清单：`docs/05-roadmap/trial-readiness.md`
- 历史决策：`docs/06-archive/work-log.md`
- 远程仓库：`ssh://git@git.example.internal:2222/operator/softwiki.git`
