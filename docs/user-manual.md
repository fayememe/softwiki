# Softwiki 用户与管理员使用手册

**更新日期**：2026-06-09  
**目标读者**：系统管理员（部署/配置）& 终端使用者（研究员/分析师）

---

## 目录
1. [系统简介](#1-系统简介)
2. [安装与初始化](#2-安装与初始化)
3. [配置说明](#3-配置说明)
4. [CLI 命令参考](#4-cli-命令参考)
5. [Shell TUI 使用](#5-shell-tui-使用)
6. [MCP 工具注册](#6-mcp-工具注册)
7. [工作流示例](#7-工作流示例)

---

## 1. 系统简介

SoftWiki 是一个**领域无关的研究知识库引擎**，以 MCP（Model Context Protocol）作为能力边界，向外部 AI 工具暴露知识库的读写和检索能力。

系统对原始文献（网页、PDF）进行五类知识抽取：
- **RAG 向量/关键词索引**（混合检索）
- **ClaimDB**（声明/立场抽取）
- **知识图谱**（实体+关系）
- **时间线**（时序事件）
- **LLM-Wiki**（Markdown 知识页面，可累积增重）

---

## 2. 安装与初始化

### 2.1 系统要求
- Python 3.10+（含 SQLite3）
- Node.js 18+（仅 WebUI 需要）
- opencode（Shell TUI 需要，可选）

### 2.2 安装步骤

```bash
# 1. 进入项目根目录
cd /path/to/softwiki

# 2. 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install --upgrade pip
pip install -e .

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填写 API keys

# 5. 初始化默认工作空间
./sw init
```

### 2.3 多工作空间

```bash
# 初始化新工作空间
./sw -w workspace/my-research init

# 使用指定工作空间
./sw -w workspace/my-research shell
./sw -w workspace/my-research ask "问题"

# 或使用环境变量
export WORKSPACE_DIR=/absolute/path/to/any/directory
./sw shell
```

---

## 3. 配置说明

### 3.1 环境变量（`.env`）

```bash
# Core LLM（知识抽取 / 问答 / Wiki 生成）
OPENAI_API_KEY=your_key
OPENAI_API_BASE=https://generativelanguage.googleapis.com/v1beta/
EXTRACTION_MODEL=gpt-4o-mini
ANALYSIS_MODEL=gpt-4o

# Shell / TUI 模型（独立配置，可与 Core 不同）
# SHELL_MODEL=gemini-2.5-flash
# SHELL_API_BASE=https://...
# SHELL_API_KEY=your_shell_key

# Embedding
EMBEDDING_PROVIDER=openai        # 或 local
EMBEDDING_MODEL=text-embedding-3-small

# Web Search（BYOK，三选一，可不配置）
# TAVILY_API_KEY=...
# SERPAPI_KEY=...
# BING_SEARCH_API_KEY=...

# 工作空间
WORKSPACE_DIR=workspace/default

# 运行模式
SOFTWIKI_MODE=wiki-admin         # wiki-admin / wiki-manage / wiki-work / wiki-study

# 功能开关
ENABLED_MODULES=rag,graph,claimdb,timeline,llmwiki
```

### 3.2 工作空间配置

工作空间目录下的 `configs/` 可覆盖默认配置：

| 文件 | 说明 |
|------|------|
| `scope.md` | 知识库范围定义（In Scope / Out of Scope） |
| `configs/sources.yaml` | 数据源信任级别 |
| `configs/model_profiles.yaml` | 模型参数覆盖 |
| `configs/workflows.yaml` | 工作流覆盖 |
| `configs/agents.md` | Shell agent 提示词覆盖 |

---

## 4. CLI 命令参考

```bash
# 初始化工作空间
./sw init
./sw -w workspace/my-kb init

# 摄入文档
./sw ingest --url "https://example.com/article"
./sw ingest --file /path/to/paper.pdf

# 重建检索索引
./sw index

# RAG 问答
./sw ask "你的研究问题"

# 生成 Wiki 页面
./sw wiki build --topic topic-id

# 查看工作空间状态
./sw status

# 启动 Shell TUI
./sw shell
./sw shell --mode wiki-manage
./sw shell -w workspace/my-kb

# 启动 REST API（供 WebUI 使用）
./sw api --port 8000 --host 127.0.0.1
```

---

## 5. Shell TUI 使用

Shell 是一个以 opencode 为核心的 AI 研究助手，支持四种操作模式：

| 模式 | 启动 | 权限 |
|------|------|------|
| `wiki-study` | `./sw shell --mode wiki-study` | 只读（检索/问答） |
| `wiki-work` | `./sw shell --mode wiki-work` | + Wiki 编译 |
| `wiki-manage` | `./sw shell --mode wiki-manage` | + 摄入/重建索引 |
| `wiki-admin` | `./sw shell`（默认） | 全部 |

Shell 中可使用所有 opencode 原生能力（web search、代码分析等），并额外接入 SoftWiki MCP tools。

### Fallback REPL（无 opencode 时）

若系统未安装 opencode，Shell 会退到最小 REPL 模式，支持以下指令（通过 MCP 执行）：

```
/ask <问题>         - RAG 问答
/web <查询>         - Web 搜索（BYOK）
/ingest <url|path>  - 摄入文档
/index              - 重建索引
/wiki <topic>       - 生成 Wiki 页面
/init               - 初始化工作空间
/status             - 查看状态
/help               - 帮助
/exit               - 退出
```

---

## 6. MCP 工具注册

SoftWiki MCP server 可注册到任何支持 MCP 的 AI 工具：

**Claude Desktop / Cursor 配置**（`claude_desktop_config.json` / `mcp.json`）：
```json
{
  "mcpServers": {
    "softwiki": {
      "command": "/path/to/softwiki/venv/bin/python",
      "args": ["-m", "softwiki.mcp.server"],
      "cwd": "/path/to/softwiki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwiki",
        "SOFTWIKI_MODE": "wiki-admin"
      }
    }
  }
}
```

**已暴露的 MCP tools**：

| Tool | 说明 |
|------|------|
| `status` | 工作空间状态 |
| `ingest` | 摄入 URL 或 PDF |
| `index` | 重建索引 |
| `search` | 混合检索 |
| `wiki_build` | 生成 Wiki 页面 |
| `ask` | RAG 问答 |
| `web_search` | BYOK 网络搜索（需配置 key） |

---

## 7. 工作流示例

### 摄入并分析一篇文章

```bash
# 1. 摄入
./sw ingest --url "https://example.com/research-paper"

# 2. 重建索引（首次或批量摄入后）
./sw index

# 3. 问答
./sw ask "这篇文章的核心观点是什么？"

# 4. 生成 Wiki 页面
./sw wiki build --topic my-topic
```

### 使用 Shell 进行深度研究

```bash
# 启动 Shell（wiki-manage 模式）
./sw shell --mode wiki-manage

# 在 Shell 中，AI agent 可以：
# - 使用 MCP tools 摄入、检索、编译
# - 使用 opencode 原生 web search 收集最新信息
# - 生成研究报告
```

### 多工作空间管理

```bash
# 创建专项知识库
./sw -w workspace/fintech init
./sw -w workspace/climate init

# 分别摄入不同领域文献
./sw -w workspace/fintech ingest --url "..."
./sw -w workspace/climate ingest --url "..."

# 分别使用各自的 Shell
./sw -w workspace/fintech shell
./sw -w workspace/climate shell
```
