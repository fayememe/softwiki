# softwiki: Universal Domain-Independent Research Wiki & RAG Engine

[English](#english) | [中文](#中文)

> **当前状态**：LightRAG 集成完成，WebUI 重新设计，MCP 17 tools 就绪。详见 [docs/project-status.md](docs/project-status.md)。

---

## English

**softwiki** is a domain-independent, source-grounded research intelligence and knowledge management engine. It exposes its capabilities through MCP (Model Context Protocol), allowing any MCP-compatible AI tool (Claude, Cursor, opencode, etc.) to query, ingest, and manage knowledge bases.

### Architecture

```
External AI Tools (opencode / Claude / Cursor)
        ↕  MCP
SoftWiki Core (RAG · LightRAG · ClaimDB · Timeline · LLM-Wiki)
        ↕  SQLite + Local Files / PostgreSQL (optional)
Workspace (any directory, fully isolated)
```

### 🌟 Key Features

- **MCP-First**: 17 MCP tools — `ask`, `ingest`, `index`, `search`, `wiki_build`, `lightrag_query`, `lightrag_explore`, `graph_query`, etc.
- **LightRAG GraphRAG**: Multi-hop graph traversal, incremental insertion, BFS subgraph exploration, 6 query modes (local/global/hybrid/mix/naive/bypass)
- **Workspace Isolation**: Multiple independent knowledge bases at any path
- **Hybrid Retrieval**: Dense vector + BM25 with Reciprocal Rank Fusion (RRF)
- **Multi-Layer Extraction**: Claims · Knowledge Graph (entities + relations) · Timeline events · LLM-Wiki
- **LLM-Wiki**: Auto-generated, compounding Markdown wiki pages per topic
- **WebUI**: Next.js 16 dark-theme dashboard with session management, Wikipedia-style wiki viewer, theme switching
- **Shell TUI**: opencode-powered research shell, zero dependency on Core Python APIs
- **Separated LLM/Embedding config**: LLM and embedding can use different providers (e.g., DeepSeek LLM + Gemini embedding)
- **PostgreSQL support**: Switch from JSON to PostgreSQL storage via config, no code changes
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
      "cwd": "/path/to/softwiki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwiki"
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
SoftWiki Core（RAG · LightRAG · 声明库 · 时间线 · LLM-Wiki）
        ↕  SQLite + 本地文件 / PostgreSQL（可选）
Workspace（任意路径，完全隔离）
```

### 🌟 核心特性

- **MCP 优先**：17 个 MCP tools，覆盖检索/摄入/图查询/Wiki 编译
- **LightRAG 图查询**：多跳推理、增量插入、BFS 子图遍历，支持 6 种查询模式
- **工作空间隔离**：支持任意路径的独立知识库，完全隔离
- **混合检索**：dense 向量 + BM25，RRF 融合
- **多维知识抽取**：声明 · 知识图谱 · 时序事件 · LLM-Wiki
- **LLM-Wiki**：基于 LLM 的可累积 Markdown 知识页面
- **WebUI**：Next.js 16 暗色主题仪表盘，会话管理，Wikipedia 风格阅读器
- **Shell TUI**：opencode 研究助手，对 Core 零 Python 依赖
- **LLM/Embedding 分离配置**：LLM 和 Embedding 可独立设定不同 Provider
- **PostgreSQL 支持**：配置切换，一行代码不改
- **BYOK 网络搜索**：Tavily / SerpAPI / Bing（可选）

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
      "cwd": "/path/to/softwiki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwiki"
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
