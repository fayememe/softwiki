# Naming：SWAgent / SWA / swagent

> status: ✅ frozen（2026-10-31）
> 目的：统一产品、代码、运维、销售口径，避免和 opencode 自身混淆。

## 1. 正式名称

```text
产品名：SWAgent
缩写：SWA
工程标识：swagent
底层引擎：opencode engine
```

## 2. 使用规则

| 场景 | 用词 |
|---|---|
| 销售 / Demo / UI | SWAgent |
| 口头简称 | SWA |
| 代码 / 服务 / CLI | `swagent` |
| 底层运行时 | `opencode engine` |
| 用户个人使用的 opencode | `personal opencode` |
| SWAgent 对话 | `SWAgent session` |
| opencode 内部线程 | `opencode session` |

避免单独说 “agent”：它可能指 SWAgent、opencode agent、MCP agent、AI agent。

## 3. 公开说法

不隐藏 opencode：

> SWAgent 是 SoftWiki 的 Agent 产品，底层使用 opencode 作为 engine。

不要说：

- “我们内置了一个 opencode”
- “打开 opencode”
- “opencode session”指代 SWAgent 对话

## 4. 兼容别名

当前保留：

```text
softwiki agent-web       -> legacy，继续可用
softwiki swagent         -> 推荐
/api/agent/*             -> legacy，继续可用
/api/swa/*               -> 推荐
/agent                   -> legacy 页面入口
/swagent                 -> 推荐页面入口
softwiki-agent-web.service -> legacy 服务名
```

后续可以只保留新名字，但不要一次性破坏现有部署。

## 5. Session

```text
SWAgent session
  -> opencode session（后端映射，不对外暴露）
  -> personal opencode session（完全隔离）
```

- SWAgent 的 Web/Agent 对话叫 `SWAgent session`
- 只有讨论引擎内部时才叫 `opencode session`
- 个人 opencode 的 session 不进入 SWAgent

## 6. 代码位置

- CLI：`softwiki swagent`（alias 到 `agent-web`）
- API：`/api/swa/*`（alias `/api/agent/*`）
- UI：SWAgent
- 服务：`softwiki-agent-web.service`（后续可改 `swagent.service`）
- Engine：`/opt/aitools/apps/softwiki/engine/opencode/<version>/opencode`
