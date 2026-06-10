# SoftWiki 项目状态与开发总结

**最后更新**：2026-06-09  
**状态**：五层知识架构全部打通，Phase 1 MCP tools 完整，EVA-KB 示例数据就绪

---

## 一、项目定位

SoftWiki 是一个**领域无关的研究知识库引擎**，以 MCP（Model Context Protocol）作为能力边界，向外部 AI 工具暴露知识库的读写和检索能力。

```text
外部工具（opencode / Claude / Cursor / WebUI）
        ↕  MCP
SoftWiki Core（RAG · GraphRAG · ClaimDB · Timeline · LLM-Wiki）
        ↕  SQLite + 本地文件
Workspace（用户工作空间，任意路径）
```

核心原则：**Core 只负责知识库领域业务逻辑，不承担外部 Agent 工作**。

---

## 二、项目结构

```
softwiki/
├── softwiki/
│   ├── config.py                 # 工作空间路径、环境变量加载
│   ├── mcp/
│   │   └── server.py             # MCP 服务端（FastMCP）
│   ├── cli/
│   │   ├── main.py               # Click CLI 入口（init/ingest/index/ask等）
│   │   └── shell.py              # Shell TUI（opencode wrapper，零 softwiki 依赖）
│   ├── api/
│   │   └── server.py             # FastAPI REST API（可选）
│   ├── source_store/
│   │   ├── models.py             # SQLAlchemy 模型（Document/Chunk/Claim/Entity/Event）
│   │   ├── db.py                 # SQLite 连接，auto init_tables
│   │   └── document_repo.py      # CRUD 操作
│   ├── ingestion/
│   │   ├── web_loader.py         # 网页抓取
│   │   ├── pdf_loader.py         # PDF 解析
│   │   └── dedup.py              # 哈希去重
│   ├── extraction/
│   │   ├── processor.py          # 抽取管道入口
│   │   ├── claim_extractor.py    # 声明/观点抽取（LLM）
│   │   ├── graph_extractor.py    # 实体+关系图谱抽取（LLM）
│   │   └── timeline_extractor.py # 时间线事件抽取（LLM）
│   ├── rag/
│   │   ├── chunker.py            # 文档分块
│   │   ├── embedder.py           # 向量嵌入（OpenAI / local）
│   │   ├── vector_store.py       # 本地 numpy 向量索引
│   │   ├── bm25_store.py         # BM25 稀疏索引
│   │   ├── hybrid_search.py      # 混合检索（dense + BM25）
│   │   └── citations.py          # 引用生成
│   ├── intelligence/
│   │   ├── answer_engine.py      # RAG 综合问答引擎（核心）
│   │   ├── llm_client.py         # OpenAI-compat LLM 调用封装
│   │   └── scope_guard.py        # 知识库 scope 约束检查
│   ├── wiki/
│   │   └── page_generator.py     # LLM 驱动的 Wiki 页面生成
│   └── templates/                # 默认配置模板（agent_soul.md / workflows.yaml 等）
├── workspace/
│   └── default/                  # 默认工作空间（DB + 索引 + 配置 + 导出）
├── docs/                         # 架构文档
├── web/                          # WebUI（Next.js，独立子项目）
├── sw                            # 快捷启动脚本
├── .env.example                  # 环境变量配置示例
└── pyproject.toml                # 项目依赖
```

---

## 三、已完成功能

### 3.1 Core 知识库能力

| 模块 | 状态 | 说明 |
|------|------|------|
| 文档摄入（URL / PDF） | ✅ 完整 | web_loader（含 language 检测）+ pdf_loader，哈希去重 |
| 知识抽取 | ✅ 完整 | Claim · Entity · Relationship · Event 四类 LLM 抽取，后台线程 |
| 分块与向量索引 | ✅ 完整 | ingest 时立即增量 chunk + append，无需手动 index() |
| BM25 稀疏检索 | ✅ 完整 | rank-bm25，支持增量 add_documents() |
| 混合检索 | ✅ 完整 | dense + BM25 RRF 融合，chunk 按 ID 点查 |
| RAG 问答 | ✅ 完整 | answer_engine.py，上下文窗口截断 + LLM 综合 |
| Scope 约束 | ✅ 完整 | scope_guard.py，config/scope.md 驱动 |
| Wiki 页面生成 | ✅ 完整 | page_generator.py，增量 Diff-Patch，Gemini 2.5 Pro |
| 工作空间隔离 | ✅ 完整 | WORKSPACE_DIR 任意路径，`.softwiki/` 隐藏内部数据 |
| Pipeline 文件落盘 | ✅ 完整 | raw/ → .softwiki/md/ → .softwiki/chunks/ → .softwiki/extractions/ |

### 3.2 Workspace 目录结构（当前标准）

```
workspace/my-kb/
├── raw/              # 原始来源文件（html / pdf）
├── .softwiki/        # SoftWiki 内部数据
│   ├── processed.db  # SQLite 唯一真实数据源
│   ├── md/           # 清洗后文档文本
│   ├── chunks/       # 分块 JSON
│   ├── extractions/  # LLM 抽取结果 JSON
│   └── index/        # vector_index.npz + bm25_index.pkl
├── config/           # 工作空间配置（scope.md / topics.yaml / sources.yaml）
└── exports/wiki/     # wiki_build 输出
```

### 3.3 MCP 服务（`softwiki/mcp/server.py`）

当前已暴露的 14 个 MCP tools：

| Tool 名称 | 功能 |
|-----------|------|
| `status` | 工作空间状态（文档数/分块数/声明数） |
| `ingest` | 摄入 URL 或本地 PDF，立即可检索 |
| `index` | 全量重建向量和 BM25 索引 |
| `search` | 混合检索，返回相关分块 |
| `retrieve` | 结构化检索（含 chunk_id / doc_id / score） |
| `ask` | RAG 问答（hybrid search + LLM 综合） |
| `wiki_build` | 生成指定 topic 的 Wiki 页面 |
| `wiki_read` | 读取已生成的 Wiki 页面内容 |
| `source_list` | 列出所有已摄入文档 |
| `source_preview` | 预览文档全文 |
| `graph_query` | 查询知识图谱（实体/关系） |
| `timeline_query` | 查询时间线事件（支持日期过滤） |
| `claim_query` | 查询声明/观点数据库（按 actor/topic/stance） |
| `web_search` | BYOK 网络搜索（Tavily/SerpAPI/Bing） |

**重要设计**：MCP server 用 `_stderr_print` wrapper 将所有 `print()` 重定向到 stderr，保证 stdout 的 JSON-RPC 流不被污染。

### 3.3 Shell TUI（`softwiki/cli/shell.py`）

- 本质是 **opencode wrapper**，生成工作空间隔离的 `opencode.json`
- 支持四种模式：`wiki-admin` / `wiki-manage` / `wiki-work` / `wiki-study`
- 模式通过 `SOFTWIKI_MODE` 环境变量传递给 MCP server，实现写操作权限控制
- **零 softwiki 依赖**（Phase 1 已完成）：shell.py 只用 stdlib + PyYAML，所有知识库操作通过 MCP stdio JSON-RPC 调用
- opencode 使用 `tools.websearch/webfetch: true` 启用模型原生 web search，不需要额外 API key
- Shell 独立模型配置：`SHELL_MODEL` / `SHELL_API_BASE` / `SHELL_API_KEY`（fallback 到 core 的 ANALYSIS_MODEL）
- Fallback REPL（无 opencode 时）：通过 `_call_mcp_tool()` 调用本地 MCP server

### 3.4 Web Search（BYOK）

- MCP `web_search` tool 支持三个 provider，按顺序 fallback：
  1. **Tavily**（推荐，`TAVILY_API_KEY`）
  2. **SerpAPI**（`SERPAPI_KEY`）
  3. **Bing Web Search API**（`BING_SEARCH_API_KEY`）
- 未配置时返回友好提示，不报错
- Shell 内的 `/web` 命令走相同逻辑（`_shell_web_search()`，不经过 MCP）

### 3.5 CLI

```bash
./sw init                          # 初始化工作空间
./sw ingest --url <url>            # 摄入网页
./sw ingest --file <path.pdf>      # 摄入 PDF
./sw index                         # 重建索引
./sw ask "问题"                     # RAG 问答
./sw wiki build --topic <id>       # 生成 Wiki 页面
./sw shell                         # 启动 Shell TUI
./sw -w workspace/my-kb shell      # 指定工作空间
./sw api                           # 启动 REST API
```

---

## 四、架构约定（重要）

### 子项目边界

```text
softwiki/mcp/     → SoftWiki Core 的 MCP 暴露层（唯一对外接口）
softwiki/cli/     → Shell TUI（opencode wrapper，对 Core 零依赖）
softwiki/api/     → REST API（可选，供 WebUI 使用）
web/              → WebUI（Next.js，独立子项目，通过 API 访问 Core）
```

### 依赖方向

```
Web UI    → REST API  → Core
Shell     → MCP       → Core
外部 Agent → MCP       → Core

Core 对任何外部工具零依赖。
```

### 工作空间（Workspace）

- 默认路径：`workspace/default/`（可通过 `WORKSPACE_DIR` 指定任意绝对路径）
- 结构：`.softwiki/`（内部数据）+ `raw/` + `config/` + `exports/`
- 每个工作空间完全隔离，切换只需改 `WORKSPACE_DIR`

---

## 五、尚未完成 / 下一步

### 5.1 MCP 层 ✅ Phase 1 完成

所有 Phase 1 tools 已实现，详见 3.3 节。

### 5.2 GraphRAG 升级（进行中）

- 当前图谱实现：简单 LLM 抽取 → SQLite 存储 → SQL 过滤查询
- 不支持多跳推理、社区检测、全局摘要
- 计划：集成 **LightRAG**，支持增量 insert 和真正的图遍历

### 5.3 index() 增量模式

- 当前 `index()` 是全量重建（delete all + recreate）
- `ingest()` 已支持单文档增量 append，但 `index()` 仍为全量
- 规划：`index()` 只处理 status=pending/indexed_stale 的文档

### 5.4 远程 MCP（Phase 2）

- 目前 MCP 只支持本地 stdio 模式
- 规划：支持 HTTPS + Bearer token 远程访问

### 5.5 Token / RBAC（Phase 3）

- 目前 mode 约束通过环境变量实现（honor system）
- 规划：正式 token 机制，每个 token 绑定 role + workspace 访问权限

### 5.6 WebUI

- `web/` 目录存在但未完整实现
- 规划：Next.js 前端，通过 REST API 连接 Core

### 5.7 其他

- `mcp` 包尚未从 pyproject.toml 列为正式依赖
- `ingestion/web_loader.py` BeautifulSoup 解析复杂页面效果有限

---

## 六、关键环境变量

```bash
# 工作空间
WORKSPACE_DIR=workspace/default       # 工作空间绝对或相对路径

# Core LLM（用于抽取 / 问答 / Wiki 生成）
OPENAI_API_KEY=...
OPENAI_API_BASE=https://generativelanguage.googleapis.com/v1beta/
EXTRACTION_MODEL=gpt-4o-mini
ANALYSIS_MODEL=gpt-4o

# Shell / TUI（独立，可与 Core 不同）
SHELL_MODEL=gemini-2.5-flash
SHELL_API_BASE=https://...
SHELL_API_KEY=...

# Embeddings
EMBEDDING_PROVIDER=openai             # 或 local
EMBEDDING_MODEL=text-embedding-3-small

# Web Search（BYOK，三选一）
TAVILY_API_KEY=...
SERPAPI_KEY=...
BING_SEARCH_API_KEY=...

# 运行模式
SOFTWIKI_MODE=wiki-admin              # wiki-admin / wiki-manage / wiki-work / wiki-study
SOFTWIKI_SESSION_ID=default

# 功能开关
ENABLED_MODULES=rag,graph,claimdb,timeline,llmwiki
```

---

## 七、启动方式

```bash
# 安装依赖
python -m venv venv
source venv/bin/activate
pip install -e .

# 复制并填写配置
cp .env.example .env

# 初始化默认工作空间
./sw init

# 启动 Shell（需要 opencode 已安装）
./sw shell

# 启动 MCP server（供外部 AI 工具直接使用）
python -m softwiki.mcp.server

# 启动 REST API
./sw api
```

MCP server 可直接在 Claude Desktop / Cursor / opencode 等工具的配置中注册：

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
