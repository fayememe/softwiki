# 界面信息架构（UI IA）

> 状态：✅ frozen（2026-11-26，操作员逐项确认）
> 实现：`web/`（`components/Sidebar.tsx`、`app/page.tsx` 及各面板）

## 1. 原则

1. **一个库一个实例，但一个实例可以有多个库**。首页展示本实例可见的全部库，不是当前库。
2. **不自动改变界面布局**：侧栏折叠只由用户点击触发。
3. **能力有就接真的，没有就明说**：禁用按钮必须给出原因，不做假成功态。
4. **同一个概念只有一个入口**：图谱只有一个入口（内嵌 Graph Studio），Wiki 门户只有一个入口（内嵌 + 面板内助手）。

## 2. 侧栏结构

```
softwiki            [语言] [折叠]
知识库下拉 / 角色下拉

总览（Home，跨库）

知识库 ─────────────
  资料流程         ← 各环节状态与依赖（新增 2026-11-26）
  文档
  论断
  图谱             ← 内嵌 Graph Studio
  时间线
  Wiki 门户        ← 内嵌 /wikiweb
  导入             (wiki-work+)
  冲突             (wiki-work+)

管理 ─────────────── (wiki-admin+)
  知识库管理       ← 原「新建库」/ KbWizard
  用户             ← AdminPanel

────────────────────
会话            [+]
  会话列表（常驻，点击即切到对话）
```

- 角色门槛：`wiki-study < wiki-work < wiki-manage < wiki-admin`；单品门槛用于导入/冲突，整组门槛用于管理组。
- 会话列表不再依赖「对话」面板是否存在，任何面板下都可见。
- 会话按知识库隔离：`localStorage` key = `softwiki_sessions:<kb>`；切库后不串历史。

## 3. 主区右上角

固定操作簇 `.top-actions`：`[助手] [主题]`，横向排列、8px 间距，`top:12px right:14px`。
助手打开时高亮（`.icon-btn-active`）。各面板头部右侧预留约 108px，避免内容被压。

右侧两个「侧栏」都可以拖动左边框调宽，逻辑在 `lib/use-resizable-width.ts`（pointer capture +
双击复位 + localStorage）：

| 面板 | 默认 | 范围 | 存储 key |
|---|---|---|---|
| 助手（AgentSidePane） | 420 | 320–760（同时给主区留 520） | `softwiki_assistant_width` |
| Wiki 右侧栏 | 300 | 240–720（给预览留 320） | `softwiki_wiki_rail_width` |

## 3.1 资料流程（`/api/kb/pipeline`）

一个库不是「一次性建好的东西」，而是几件产物各有触发条件和过期判定。面板把它们画成三条链路：

| 链路 | 关系 |
|---|---|
| ① 检索 | 文档 → 切块 + 向量化 → 检索索引（chunks / vectors / BM25） |
| ② 知识 | 文档 → 抽取 → 论断 → 投影 → 图谱 / 时间线 |
| ③ 发布 | 论断 → 组合 → Wiki 页面 → 发布 → 静态门户 |

每张卡片给出 `ok / 生成中 / 需更新 / 无数据 / 部分缺失` 与计数，后端一次性算好：

- 索引过期：`chunks == 0`、或存在无分块文档、或 pg 向量数 < chunk 数；
- 论断在跑：存在 `pending/extracting` 文档；
- 图谱/时间线「部分缺失」：有 claim 未挂到边/事件；
- Wiki 在跑/过期：`wiki_rebuild_tasks` 的 pending+running、`wiki_artifact_states.stale_at`；
- 门户过期：`exports/wikiweb/<kb>/index.html` 的 mtime 早于最新 `WikiArtifactState.built_at`。

有生成中的环节时前端 5s 轮询，否则 30s。索引卡片的「重建索引」仍是全量重建，按钮上明确提示。

## 3.2 助手（Work / Manage / Admin）

助手是**知识库管理助手**，不是研究聊天：

| 项目 | opencode agent | 能做什么 | 人格 |
|---|---|---|---|
| Work | `wiki-work` | 检索、读 wiki、提出变更方案（不能导入/索引/发布） | 管理员人格（只读受限） |
| Manage | `wiki-manage` | 导入、重建索引、继续抽取、生成主题页/实体页、审批计划 | 管理员人格 |
| Admin | `wiki-admin` | 全部（workspace/modules 除外） | 管理员人格 |
| （研究入口） | `wiki-research` / `wiki-study` | 只读问答，要求页码引用 | 研究人格 |

两条容易搞错的地方（都已修）：

1. **人格按 mode 选**：`AGENTS_<mode>.md` 之前用同一个 soul（研究人格），
   所以 Manage 也会用 `softwiki_ask` 写答案。现在 work/manage/admin 用管理员人格，
   研究/学习模式用研究人格。
2. **MCP 服务整进程只有一个角色**：javis 上 `SOFTWIKI_ROLE=wiki-study`，管理助手的写工具
   全被拒。现在 agent 的 remote MCP 连接发送 `x-softwiki-role: wiki-manage`
   （`SOFTWIKI_AGENT_MCP_ROLE` 可覆盖）；项目级最小权限仍由 opencode 的 deny 列表保证。

管理工具（服务端实际暴露：`softwiki.mcp.sse`）：`pipeline_status`、`status`、
`resume_extraction`、`rebuild_index`、`wiki_build`、`wiki_subject_build`、
`ingest_url`/`ingest_file`、`list_documents`/`list_claims`、`search`/`ask`（核对用）等。

验收（javis 实测）：问「检查流程状态，只报告，不要重建」→ 只调用 `softwiki_pipeline_status`，
回答里列出 tsmckb 的检索/知识/发布三链状态并指出 4 条边、44 个事件、Wiki/门户待更新。

## 4. 图谱

- `components/GraphStudioPanel.tsx` 是唯一实现；`app/graph-studio/page.tsx` 只是薄包装（保留旧书签）。
- 交互约定：
  - 左键点击节点 = 选中；双击 = 展开邻域；左键空白 = 什么都不发生。
  - **只有按住中键拖动才平移**（`onMouseDown` 判 `button===1`）。
  - 滚轮以光标为中心缩放。
  - 头部提供 `fit` 按钮。
- 力学约束：节点间距 ≥30px、单对力与速度都有上限（6px/tick）、阻尼 0.9、中心引力、软边界、按总动能提前停帧。
- 展开新节点以父实体为锚点生成；若新节点落在视野外，自动 fit 一次（不打断用户手动缩放）。

## 5. Wiki 面板

`components/WikiWebPanel.tsx`，两个 tab：

| tab | 内容 |
|---|---|
| 门户预览 | `iframe /wikiweb`（静态快照），右上「在新标签打开」 |
| 页面与生成 | 原 `WikiPagesPanel`：主题页列表、批量生成、agent 提案（`/api/wiki/plans`）的批准/拒绝 |

右侧栏（宽度可拖动，240–720px，双击分隔条复位，宽度记在 localStorage）：

- 生成：跳到「页面与生成」；「重建门户」**禁用**——当前只有 `scripts/wikiweb_build.py`，且 Next 启动时才枚举目录，需要重启 web。
- Wiki 助手：打开右侧助手面板并落在 `manage` 项目（唯一可提交 wiki 变更的 profile）。
- 状态：当前库、是否已生成、主题页数量。

## 6. 对话

- 默认且主要的引擎是 **agent（SWAgent / opencode）**。
- Quick（RAG 快速检索）保留为**次级入口**：空状态里的「使用快速检索（无助手工具链）」，
  进入后 modeBar 显示「快速检索模式 · 切回助手」。
- 理由：agent 自己会调 `softwiki_search/ask`；但 Quick 是稳定带页码引用的降级路径，demo 失败预案需要它。

## 7. 首页 / 总览

- `GET /api/kb/stats`：遍历本实例可见的库（注册表 ∩ `kb_scope`），逐库读自己的数据库取计数，30s 缓存。
  打不开的库返回 `available=false` + `reason`，前端灰显，不计入合计。
- 前端：合计行（文档/分块/论断/实体/关系/事件）+ 每库卡片（可用性、当前库标记、点击切换或跳转 `web_url`）。

## 8. 已知边界 / 待办

- **trial-host 两栈各只服务一个库**（`SOFTWIKI_STACK_ROOT` 私有根），所以 trial 首页只会显示 1 个库；
  javis（单栈多库）会显示全部。要跨栈总览需要另议（远端探测或合并栈）。
- 门户重建按钮要等一个后台任务 API（`POST /api/wiki/site/rebuild` 之类）。
- 侧栏会话（localStorage）与面板内 agent session 选择器仍是两个概念，后续可合并。
- 旧全局会话 key `softwiki_sessions` 未迁移；升级后历史会话不显示（数据仍在 localStorage）。
- 旧 `GraphPanel.tsx` 已不再被引用，可删除。
- 拖动分隔条时必须用 pointer capture（否则指针越过 iframe 后事件被 iframe 吃掉，拖动会卡在起始宽度）。
