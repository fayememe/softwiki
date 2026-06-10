# softwiki: Universal Domain-Independent Research Wiki & RAG Engine

[English](#english) | [中文](#中文)

> **当前状态**：核心功能完整，MCP 层就绪，Shell 独立化完成。详见 [docs/project-status.md](docs/project-status.md)。

---

## English

**softwiki** is a domain-independent, source-grounded research intelligence and knowledge management engine. It exposes its capabilities through MCP (Model Context Protocol), allowing any MCP-compatible AI tool (Claude, Cursor, opencode, etc.) to query, ingest, and manage knowledge bases.

### Architecture

```
External AI Tools (opencode / Claude / Cursor)
        ↕  MCP
SoftWiki Core (RAG · GraphRAG · ClaimDB · Timeline · LLM-Wiki)
        ↕  SQLite + Local Files
Workspace (any directory, fully isolated)
```

### 🌟 Key Features

- **MCP-First**: All knowledge operations exposed as MCP tools — `ask`, `ingest`, `index`, `search`, `wiki_build`, `status`, `web_search`
- **Workspace Isolation**: Multiple independent knowledge bases at any path (`workspace/my-workspace/`, `/any/absolute/path/`)
- **Hybrid Retrieval**: Dense vector + BM25 with Reciprocal Rank Fusion (RRF)
- **Multi-Layer Extraction**: Claims · Knowledge Graph (entities + relations) · Timeline events
- **LLM-Wiki**: Auto-generated, compounding Markdown wiki pages per topic
- **Shell TUI**: opencode-powered research shell, zero dependency on Core Python APIs
- **BYOK Web Search**: Tavily / SerpAPI / Bing (optional, shell uses model-native search)

---

### 🛠️ Quick Start

#### 1. Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, OPENAI_API_BASE, model names
```

#### 2. Initialize Workspace

```bash
# Default workspace
./sw init

# Custom workspace
./sw -w workspace/my-workspace init
```

#### 3. Ingest & Index

```bash
./sw -w workspace/my-workspace ingest --url "https://example.com/article"
./sw -w workspace/my-workspace index
```

#### 4. Ask & Build Wiki

```bash
./sw -w workspace/my-workspace ask "What are the key findings?"
./sw -w workspace/my-workspace wiki build --topic topic-alpha
```

#### 5. Shell TUI (requires opencode)

```bash
./sw shell                          # wiki-admin mode (default)
./sw shell --mode wiki-study        # read-only mode
./sw -w workspace/my-workspace shell
```

#### 6. Register as MCP Server

Add to your AI tool's MCP config:
```json
{
  "mcpServers": {
    "softwiki": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "softwiki.mcp.server"],
      "cwd": "/path/to/softwki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwki"
      }
    }
  }
}
```

---

### 🧪 Tests

```bash
PYTHONPATH=. ./venv/bin/pytest
```

---

## 中文

**softwiki** 是一个领域无关的研究知识库引擎，以 MCP（Model Context Protocol）为能力边界，向外部 AI 工具暴露知识库的读写和检索能力。

### 核心架构

```
外部 AI 工具（opencode / Claude / Cursor）
        ↕  MCP
SoftWiki Core（RAG · 图谱 · 声明库 · 时间线 · LLM-Wiki）
        ↕  SQLite + 本地文件
Workspace（任意路径，完全隔离）
```

### 🌟 核心特性

- **MCP 优先**：所有知识库操作通过 MCP tools 暴露：`ask`、`ingest`、`index`、`search`、`wiki_build`、`status`、`web_search`
- **工作空间隔离**：支持任意路径的独立知识库（`workspace/my-workspace/`、`/any/path/`）
- **混合检索**：dense 向量 + BM25，基于 RRF 融合
- **多维知识抽取**：声明/立场 · 知识图谱（实体+关系）· 时序事件
- **LLM-Wiki**：基于 LLM 的可累积 Markdown 知识页面
- **Shell TUI**：以 opencode 为核心的研究助手，对 Core Python 零依赖
- **BYOK 网络搜索**：Tavily / SerpAPI / Bing（可选），Shell 使用模型原生搜索

---

### 🛠️ 快速上手

#### 1. 安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
cp .env.example .env
# 编辑 .env，填写 OPENAI_API_KEY、OPENAI_API_BASE 等
```

#### 2. 初始化工作空间

```bash
# 默认工作空间
./sw init

# 自定义工作空间
./sw -w workspace/my-workspace init
```

#### 3. 摄入与索引

```bash
./sw -w workspace/my-workspace ingest --url "https://example.com/article"
./sw -w workspace/my-workspace index
```

#### 4. 问答与 Wiki 生成

```bash
./sw -w workspace/my-workspace ask "核心发现是什么？"
./sw -w workspace/my-workspace wiki build --topic topic-alpha
```

#### 5. Shell TUI（需要 opencode）

```bash
./sw shell                          # wiki-admin 模式（默认，全权限）
./sw shell --mode wiki-study        # 只读模式
./sw -w workspace/my-workspace shell
```

#### 6. 注册为 MCP Server

在 AI 工具的 MCP 配置中添加：
```json
{
  "mcpServers": {
    "softwiki": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "softwiki.mcp.server"],
      "cwd": "/path/to/softwki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwki"
      }
    }
  }
}
```

---

### 📚 文档

| 文档 | 说明 |
|------|------|
| [docs/project-status.md](docs/project-status.md) | ⭐ 项目状态与开发总结（主要参考） |
| [docs/user-manual.md](docs/user-manual.md) | 用户与管理员使用手册 |
| [docs/system-mapping.md](docs/system-mapping.md) | 系统架构层级映射 |
| [docs/model-guide.md](docs/model-guide.md) | 模型选型与配置指南 |
| [docs/workspace_structure.md](docs/workspace_structure.md) | 文件系统与工作空间结构 |
| [docs/technical-implementation.md](docs/technical-implementation.md) | 技术白皮书 |
| [docs/application-system.md](docs/application-system.md) | 架构讨论参考（非设计要求） |

---

### 🧪 运行测试

```bash
PYTHONPATH=. ./venv/bin/pytest
```
