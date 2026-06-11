# Shell TUI 使用指南

> **范围**: SoftWiki Shell TUI 的启动、模式、命令、搜索配置和 Fallback REPL。
> **前置阅读**: [CLI 命令参考](../03-operations/cli.md) | [安装与设置](../03-operations/setup.md)

---

## 启动

```bash
./sw shell                          # 默认 wiki-admin 模式
./sw shell --mode wiki-study        # 只读模式
./sw shell -w workspace/my-kb       # 指定工作空间
./sw shell -m gemini-2.5-pro        # 指定模型
./sw shell -s round-2               # 自定义会话后缀名
```

Shell 启动时显示 banner，包含工作空间、模式、会话名、模型、可用工作流和 MCP 工具列表。按任意键进入 TUI。

### 选项

| 选项 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--workspace` | `-w` | `str` | `WORKSPACE_DIR` 或 `workspace/default` | 工作空间路径或名称 |
| `--model` | `-m` | `str` | `ANALYSIS_MODEL` 或 `gemini-2.5-flash` | 分析用模型 |
| `--session` | `-s` | `str` | `None` | 自定义会话名称后缀 |

---

## 四种模式

Shell 根据 `SOFTWIKI_MODE` 环境变量决定操作权限。通过 `--mode` 参数指定。

| 模式 | 权限 | 可用操作 | 禁用操作 |
|------|------|----------|----------|
| `wiki-admin` | 全部操作 | ingest / index / wiki build / ask / web / init / status | 无 |
| `wiki-manage` | 摄入/索引/发布 | ingest / index / wiki build / ask / web / status | 无 |
| `wiki-work` | 只读 + Wiki 编译 + staging 提交 | wiki build / ask / web / status / submit 工作流 | ingest / index |
| `wiki-study` | 只读 | ask / web / status | ingest / index / wiki build |

### 模式详细规则

**wiki-study**（只读模式）:
- 可使用 websearch 进行研究，可检查状态
- 禁止调用 `softwiki_ingest`、`softwiki_index`、`softwiki_wiki_build` 或任何写操作
- 不可提交研究结果

**wiki-work**（工作模式）:
- 可使用 websearch 进行研究
- 禁止直接调用 `softwiki_ingest` 或 `softwiki_index`
- 研究中发现的有价值来源，可通过 `submit` 工作流暂存到 session 输出目录（`output/{session_id}/`），供 manager 审核
- 不可修改规范知识库

**wiki-manage**（知识管理）:
- 可执行 ingest、index、wiki build
- 可审核/发布来自 wiki-work 用户的提交

**wiki-admin**（管理员）:
- 所有操作均允许

---

## Fallback REPL（无 opencode）

当系统未安装 `opencode` 可执行文件时，Shell 自动降级为 Fallback REPL — 一个轻量级命令行客户端，通过 MCP 协议与 SoftWiki 服务端通信。

### 启动 Fallback REPL

```bash
./sw shell
# 输出: [opencode not found – running minimal MCP client shell]
```

### Fallback REPL 命令

| 命令 | 说明 | 模式限制 |
|------|------|----------|
| `/ask <question>` | 查询知识库（通过 MCP `ask` 工具） | 无 |
| `/web <query>` | Web 搜索（BYOK，见搜索配置） | 无 |
| `/ingest <url\|path>` | 摄入文档（URL 或本地 PDF 路径） | 需 wiki-admin 或 wiki-manage |
| `/index` | 重建搜索索引 | 需 wiki-admin 或 wiki-manage |
| `/wiki <topic>` | 编译指定主题的 Wiki 页面 | 需 wiki-admin、wiki-manage 或 wiki-work |
| `/init` | 初始化工作空间结构 | 需 wiki-admin 或 wiki-manage |
| `/status` | 查看工作空间状态 | 无 |
| `/help` | 列出所有可用命令 | 无 |
| `/exit` | 退出 Shell | 无 |

> Fallback REPL 中的 `/ingest`、`/index`、`/init` 操作需要用户确认（`[y/N]`）。`/wiki` 在 wiki-study 模式下被禁用。

---

## 搜索配置

Shell 支持两种搜索路径：opencode 原生 websearch（默认）和独立 web 搜索配置。

### 默认搜索（opencode 原生）

Shell 生成的 opencode 配置中，`tools.websearch` 默认为 `true`，由 opencode 原生 websearch 能力处理。无需额外配置。

### 独立搜索 MCP（客户端侧）

Shell 按优先级自动配置客户端侧搜索 MCP，不经过 SoftWiki 服务端：

| 优先级 | 提供商 | 环境变量 | MCP 命令 |
|--------|--------|----------|----------|
| 1 | Exa | `EXA_API_KEY` | `npx -y exa-mcp-server` |
| 2 | Tavily | `TAVILY_API_KEY` | `npx -y tavily-mcp` |
| 3 | DuckDuckGo | 无需 API Key | 通过 webfetch 原生处理 |

设置方式：

```bash
# 方案一：Exa（推荐）
export EXA_API_KEY=your-exa-key-here
./sw shell

# 方案二：Tavily
export TAVILY_API_KEY=your-tavily-key-here
./sw shell
```

> 如果同时设置了 `EXA_API_KEY` 和 `TAVILY_API_KEY`，Exa 优先。两个都未设置时回退到 DuckDuckGo。

### Fallback REPL 中的搜索

Fallback REPL 的 `/web` 命令使用 `_shell_web_search()` 函数，支持以下 BYOK 提供商（按优先级）：

| 优先级 | 提供商 | 环境变量 |
|--------|--------|----------|
| 1 | Tavily | `TAVILY_API_KEY` |
| 2 | SerpAPI | `SERPAPI_KEY` |
| 3 | Bing | `BING_SEARCH_API_KEY` |

若均未设置，返回配置提示信息。

---

## 独立模型配置

Shell 的 LLM 模型独立于 Core 模型。可通过以下环境变量配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SHELL_MODEL` | Shell 使用的 LLM 模型 | 回退到 `ANALYSIS_MODEL`，再回退到 `gemini-2.5-flash` |
| `SHELL_API_BASE` | API 端点 | 回退到 `OPENAI_API_BASE`，再回退到 Google Gemini 端点 |
| `SHELL_API_KEY` | API 密钥 | 回退到 `OPENAI_API_KEY` |

```bash
# 使用独立模型
export SHELL_MODEL=gemini-2.5-pro
export SHELL_API_BASE=https://generativelanguage.googleapis.com/v1beta/
export SHELL_API_KEY=your-api-key
./sw shell

# 或通过命令行覆盖
./sw shell -m claude-sonnet-4-20250514
```

### 模型回退链

```
SHELL_MODEL → ANALYSIS_MODEL → gemini-2.5-flash
SHELL_API_BASE → OPENAI_API_BASE → https://generativelanguage.googleapis.com/v1beta/
SHELL_API_KEY → OPENAI_API_KEY → (无默认值)
```

---

## 工作流

Shell 加载 `softwiki/templates/workflows.yaml` 中的默认工作流定义，并与工作空间 `config/workflows.yaml` 深度合并。可用工作流显示在启动 banner 的 `Workflows` 行中，以 `/workflow_name` 形式列出。

预定义工作流包括：`research`、`wiki-compile`、`contribute`、`submit`、`simple-q&a`。

---

## 架构说明

Shell 在工作空间的隔离运行时目录（`.softwiki_runtime/{ws_name}_{hash}/`）中生成独立的 opencode 配置，确保：

- 会话完全独立于用户的全局 opencode 会话
- XDG_CONFIG_HOME 和 XDG_DATA_HOME 指向运行时目录
- 自动清理工作空间中的遗留配置文件（AGENTS_*.md、opencode.json、.claude、.opencode 等）
- 全局 TUI 插件列表和 node_modules 通过符号链接复用
