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

右侧栏：

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
