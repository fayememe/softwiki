# Chat UX（参考 opencoco 的会话式聊天）

> status: 🚧 讨论中（2026-11-10）
> 范围：**只参考 opencoco 的 chat 交互与数据流**；workflow / report / wiki / claim / conflict / KB 作用域等业务流全部沿用我们自己的实现。
> 参考代码：`agenthub`（opencoco）`app/static/chat.js`（约 2.4k 行，`EventSource` 消费 opencode 事件流）。

## 1. 目标 / 非目标

**目标**

1. 把 SWAgent 从「发一条、等 30s、拿一段」升级成真正的 opencode 会话客户端：流式 parts、工具卡片、停止/重生成、会话列表与恢复。
2. Quick 模式不再像搜索框：至少推送「检索 → 融合 → 生成 → 引用」阶段事件，并为后续 token 流留出契约。
3. 两种模式共用同一套消息渲染层，但数据源独立：
   - Quick：`AnswerEngine` → `answer + sources`；
   - SWAgent：opencode 会话 → `parts`。
4. 保留全部既有业务入口：workflow 选择、Report、Wiki Prompt Studio、Claims / Conflicts、KB 切换、role/capability。

**非目标（明确不做）**

- 不做 opencoco 的舰队驾驶舱：多节点树、每节点代理端口、Basic Auth 注入、Coco、skillcell、Terminal。
- 不做跨会话 attention inbox（除非未来开启写工具，见 §7 开放问题）。
- 不移植 opencoco 代码；只复刻交互模型与事件契约，用 Next.js + TS 重写。

## 2. 现状与差距（结论先行）

我们的 chat 薄，不是布局问题，是**数据流是一次性的**：

| 维度 | 现状 | 证据 |
|---|---|---|
| SWAgent 数据流 | 服务端阻塞轮询，跑完才返回终态 JSON | `softwiki/api/server.py:643`（`/api/agent/ask`） |
| 流式 | Quick / Agent 均无 | `web/components/ChatPanel.tsx:117-151` |
| 工具展示 | 只显示 steps 数量 + 名称 | `web/components/ChatMessage.tsx:37`（`ResearchSteps`） |
| 权限 / 提问 | 无 UI | 后端仅有 abort/delete（`server.py:718`） |
| 会话 | localStorage 单一列表，opencode 侧仅存 id | `web/app/page.tsx:28`（`softwiki_sessions`） |
| 停止 / 重生成 | 有 abort API，无 UI 入口 | `server.py:718` |
| 前端体量 | ChatPanel 411 行 / ChatMessage 276 行 | — |

opencoco 的关键做法：前端直接 `new EventSource(/global/event)`（`chat.js:1471`），按 `message.updated` / `message.part.updated` / `message.part.delta` 增量维护 `message.parts`（`chat.js:1326-1387`），并把 `permission.asked` / `question.asked` 渲染成内联卡片（`chat.js:1418-1445`）。**这套模型可以直接用，但代理层要放在我们后端。**

## 3. 目标交互

### 3.1 统一消息模型（前端）

```ts
type PartType = 'text' | 'tool' | 'step' | 'reasoning' | 'file' | 'error';

interface MessagePart {
  id: string;
  type: PartType;
  text?: string;              // text / reasoning
  tool?: string;              // tool 名称，如 softwiki_search
  state?: {                   // tool 状态
    status: 'pending' | 'running' | 'completed' | 'error';
    input?: unknown;
    output?: string;
    title?: string;
    error?: string;
  };
  time?: { start?: number; end?: number };
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  parts: MessagePart[];
  order: string[];            // part 渲染顺序
  info?: { model?: string; agent?: string; tokens?: number; cost?: number; error?: string };
  sources?: Source[];         // Quick / Agent 解析出的 KB 来源
  mode: 'quick' | 'agent';
}
```

- `sources` 仍然走现有 `SourceDrawer`；Agent 的来源由 `softwiki_search/ask` 的 tool 输出解析（沿用 `_agent_sources`，`server.py`）。
- 工具卡片：可折叠，显示名称、状态、输入摘要、输出（截断 + 展开），与 opencoco 的 `chat-tool` 一致；不再只显示计数。

### 3.2 交互清单（P0）

- 流式文本（`message.part.delta` 逐段追加）。
- 工具卡片实时从 `running → completed`。
- 停止：复用 `/api/agent/session/{id}/abort`，2s 内反馈。
- 重生成：删除最后一条 assistant，重新发送同一问题。
- 会话列表：以 opencode `/session` 为真相，按 KB 打标；localStorage 只存 UI 偏好与标题覆盖。
- GFM 表格（`remark-gfm`），代码块高亮保持现状。
- 错误气泡：`session.error` 与 HTTP 失败统一渲染，附「重试」。

### 3.3 业务流保持不变

| 业务 | 入口 | 变更 |
|---|---|---|
| Quick 模式 / mode / workflow | ChatPanel modeBar | 保留 |
| Report 生成与下载 | modeBar Report | 保留 |
| Wiki Prompt Studio / 页面 | Sidebar / WikiPanel | 保留 |
| Claims / Conflicts | Sidebar 面板 | 保留 |
| KB 切换 | KnowledgeBaseSelector | 保留；会话需绑定 KB（见 §7） |
| role / capability | RoleSelector + 后端 guard | 保留 |

## 4. 架构与契约

### 4.1 事件代理放在 FastAPI

```
Browser (Next)  --GET /api/agent/events?session_id=...-->  FastAPI SSE proxy
                                                            |
                                                            +--> GET {AGENT_WEB_URL}/event (opencode)
```

理由：统一鉴权/角色、按 session 过滤、脱敏、避免浏览器跨源直连 opencode；SSE 断开重连由后端兜底。

- 端点：`GET /api/agent/events`（`StreamingResponse`，`text/event-stream`）。
- 过滤：只转发目标 `session_id` 的事件 + 全局 `permission/question` 中相关项；心跳 15s。
- 重连：支持 `Last-Event-ID`，客户端指数退避。
- 降级：若 opencode 无 `/event`（版本不匹配），自动回落到现有轮询 `/api/agent/ask`，前端标记「非流式」。

### 4.2 事件契约（opencode 1.19.5）

| 事件 | UI 行为 |
|---|---|
| `message.updated` | upsert 消息元信息（model/agent/tokens/error） |
| `message.part.updated` | upsert part（text/tool/step/reasoning/file） |
| `message.part.delta` | 追加到 part.text（流式） |
| `message.part.removed` | 移除 part |
| `session.status` | 更新运行状态徽标 |
| `session.idle` / `session.execution.*` | 结束 loading，落盘 |
| `session.error` | 错误气泡 |
| `permission.asked` / `permission.replied` | 内联卡片（默认只读模式下预计不出现） |
| `question.asked` / `question.replied` / `question.rejected` | 内联问答卡 |
| `session.updated` / `session.deleted` | 刷新会话列表 |

> 事件名以 pin 的 opencode 版本为准，落地前写**契约测试**（录一份真实事件流做 fixture）。

### 4.3 Quick 流式

- P1 先做**阶段事件**而非 token：`stage: retrieving` → `stage: fusing` → `stage: answering` → `answer` → `sources` → `citation_check`。
- 若后续要做 token 流，`AnswerEngine.ask` 需改成生成器；这是独立改动，不在 P0。

## 5. 分期与验收

### P0 — 会话内核（1–2 周）

- [ ] FastAPI `GET /api/agent/events` SSE 代理（session 过滤 + 心跳 + Last-Event-ID）
- [ ] 前端 parts store + 流式渲染 + 工具卡片
- [ ] 停止 / 重生成 / 错误重试
- [ ] 会话列表（opencode 为真相，按 KB 打标）
- [ ] 降级路径（无 SSE → 轮询）

**验收**：问一个跨文档问题（如 CM55 + NIC-400），文本逐段出现；`softwiki_search` / `softwiki_ask` 工具卡片实时变绿并可展开；点停止 2s 内结束；刷新页面能恢复同一会话；断网重连后继续。

### P1 — Quick 阶段事件（3–5 天）

- [ ] `/api/ask` SSE（阶段事件 + sources + citation_check）
- [ ] 前端阶段条 + 引用高亮

**验收**：Quick 提问时出现「检索 → 融合 → 生成」，答案带可点击页码引用与 citation_check 警告。

### P2 — wiki 专属（约 1 周）

- [ ] 消息 pin 文档/claim；答案一键存为 wiki artifact / claim 提案
- [ ] 聊天右侧上下文：相关 Claims / Conflicts / 文档
- [ ] 「引用到页面」

**验收**：从答案一键生成 wiki 草稿并进入 stale/rebuild 流程，且可在 WikiPanel 看到。

## 6. 影响文件（预估）

- `softwiki/api/server.py`：新增 SSE 端点、事件过滤与降级开关
- `web/lib/api.ts`：事件订阅 API 与 parts 类型
- `web/components/ChatPanel.tsx`：瘦身为容器
- 新增：`web/components/chat/{MessageList,PartRenderer,ToolCard,PendingCard,Composer}.tsx`
- `web/app/page.tsx`：会话列表接线（opencode 真相 + local 标题）
- `web/package.json`：`remark-gfm`

## 7. 风险与开放问题

- **opencode 事件 schema 漂移**：pin 1.19.5；先写 fixture 契约测试；不匹配则降级轮询。
- **Next 代理 SSE**：需关闭缓冲、放宽超时（已有 `proxyTimeout=300_000`）；必要时用 Next route handler 直转。
- **只读定位 vs 权限卡片**：SWAgent 现为只读（写工具 deny），`permission.asked` 预计不触发。是否开放写工具是**独立安全决策**，不在本设计内自动放开。
- **多 KB 作用域**：workspace 是进程级全局（已知并发问题）。需先定「会话 → KB」绑定方式；P0 只做单 KB 标注，不解决并发切换。
- **双源真相**：opencode 会话 vs localStorage。决定：opencode 为唯一真相，local 只存 UI 状态。

**待定**

1. SWAgent 是否开放写工具？（决定 permission UI 是否进 P0）
2. Quick 是否要 token 流，还是阶段事件即可？
3. 会话→KB：一库一会话，还是 session metadata 记录 workspace？

## 8. 决策记录

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 只参考 opencoco 的 chat，不引入舰队/代理/inbox 架构 | 我们是单实例 wiki，不是多节点运维台 |
| D2 | 不移植 opencoco 代码，按交互模型重写 | 技术栈不同（FastAPI+vanilla JS vs Next/TS） |
| D3 | SSE 代理放 FastAPI 后端 | 统一鉴权/过滤/脱敏，避免浏览器直连 opencode |
| D4 | 默认保持只读，不因本次改动开放写工具 | 安全边界独立评估 |
| D5 | Quick 与 Agent 共用渲染层、分源数据 | 避免两套消息组件 |
| D6 | 业务流（workflow/report/wiki/claim/conflict/KB）不动 | 用户明确要求沿用现有业务 |
