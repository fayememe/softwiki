# SoftWiki 项目状态与开发总结

**最后更新**：2026-06-10  
**状态**：五层知识架构全部打通，LightRAG 集成完成，WebUI 重新设计，EVA-KB 示例数据就绪

---

## 一、项目定位

SoftWiki 是一个**领域无关的研究知识库引擎**，以 MCP（Model Context Protocol）作为能力边界，向外部 AI 工具暴露知识库的读写和检索能力。

```text
外部工具（opencode / Claude / Cursor / WebUI）
        ↕  MCP
SoftWiki Core（RAG · LightRAG · ClaimDB · Timeline · LLM-Wiki）
        ↕  SQLite + 本地文件 / PostgreSQL（可选）
Workspace（用户工作空间，任意路径）
```

核心原则：**Core 只负责知识库领域业务逻辑，不承担外部 Agent 工作**。

---

## 二、项目结构

```
softwiki/
├── softwiki/
│   ├── config.py                 # 工作空间路径、环境变量加载
│   ├── graph_rag/
│   │   └── adapter.py            # LightRAG 适配器（独立存储，多后端）
│   ├── mcp/
│   │   └── server.py             # MCP 服务端（FastMCP，17 tools）
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
│   │   ├── graph_extractor.py    # 实体+关系图谱抽取（LLM，SQLite 兼容层）
│   │   └── timeline_extractor.py # 时间线事件抽取（LLM）
│   ├── rag/
│   │   ├── chunker.py            # 文档分块
│   │   ├── embedder.py           # 向量嵌入（OpenAI / local）
│   │   ├── vector_store.py       # 本地 numpy 向量索引
│   │   ├── bm25_store.py         # BM25 稀疏索引
│   │   ├── hybrid_search.py      # 混合检索（dense + BM25）
│   │   └── citations.py          # 引用生成
│   ├── intelligence/
│   │   ├── answer_engine.py      # RAG 综合问答引擎（多知识层融合）
│   │   ├── llm_client.py         # OpenAI-compat LLM 调用封装
│   │   └── scope_guard.py        # 知识库 scope 约束检查
│   ├── wiki/
│   │   └── page_generator.py     # LLM 驱动的 Wiki 页面生成
│   └── templates/                # 默认配置模板（agent_soul.md / workflows.yaml 等）
├── web/                          # WebUI（Next.js，独立子项目）
├── docs/                         # 架构文档
├── tests/                        # pytest 测试套件（31 pass / 2 known fail）
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
| RAG 问答 | ✅ 完整 | answer_engine.py，5 层知识上下文 + LLM 综合 |
| GraphRAG（SQLite 兼容层） | ✅ 完整 | 实体/关系 SQLite 存储，LIKE 过滤查询 |
| LightRAG 增强图查询 | ✅ 完整 | 增量插入、BFS 子图遍历、6 种查询模式 |
| Scope 约束 | ✅ 完整 | scope_guard.py，config/scope.md 驱动 |
| Wiki 页面生成 | ✅ 完整 | page_generator.py，增量 Diff-Patch |
| 工作空间隔离 | ✅ 完整 | WORKSPACE_DIR 任意路径，`.softwiki/` 隐藏内部数据 |
| 多后端存储 | ✅ 完整 | JSON（默认）或 PostgreSQL（配置切换） |
| LLM/Embedding 分离配置 | ✅ 完整 | LLM 和 Embedding 可独立设置不同 Provider |

### 3.2 MCP 服务（`softwiki/mcp/server.py`）

当前已暴露的 17 个 MCP tools：

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
| `graph_query` | 查询知识图谱（实体/关系，SQLite 兼容层） |
| `lightrag_query` | LightRAG 图查询（多跳推理，6 种模式） |
| `lightrag_explore` | LightRAG 子图探索（BFS 遍历） |
| `lightrag_status` | LightRAG 引擎状态 |
| `timeline_query` | 查询时间线事件（支持日期过滤） |
| `claim_query` | 查询声明/观点数据库（按 actor/topic/stance） |
| `web_search` | BYOK 网络搜索（Tavily/SerpAPI/Bing） |

**重要设计**：MCP server 用 `_stderr_print` wrapper 将所有 `print()` 重定向到 stderr，保证 stdout 的 JSON-RPC 流不被污染。

### 3.3 Shell TUI（`softwiki/cli/shell.py`）

- 本质是 **opencode wrapper**，生成工作空间隔离的 `opencode.json`
- 支持四种模式：`wiki-admin` / `wiki-manage` / `wiki-work` / `wiki-study`
- 模式通过 `SOFTWIKI_MODE` 环境变量传递给 MCP server，实现写操作权限控制
- **零 softwiki 依赖**：shell.py 只用 stdlib + PyYAML，所有知识库操作通过 MCP stdio JSON-RPC 调用
- opencode 使用 `tools.websearch/webfetch: true` 启用模型原生 web search，不需要额外 API key
- Shell 独立模型配置：`SHELL_MODEL` / `SHELL_API_BASE` / `SHELL_API_KEY`
- Fallback REPL（无 opencode 时）：通过 `_call_mcp_tool()` 调用本地 MCP server

### 3.4 WebUI（`web/`）

- **Next.js 16 + React 19** 独立前端子项目
- 暗色高级主题（Plus Jakarta Sans + DM Sans 字体）
- 5 面板路由：Chat / Ingest / Documents / Claims / Wiki
- 会话管理（创建、切换、删除、重命名，localStorage 持久化）
- 主流 AI 聊天风格：圆角气泡、SVG 图标、平滑动画
- Wikipedia 风格 Wiki 阅读器（Linux Libertine 字体、TOC 边栏）
- 主题切换：Dark / Light / Auto（右上角浮动按钮）
- 来源引用抽屉

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

## 四、LightRAG 集成

LightRAG 作为可选增强层，在现有 SQLite 实体/关系表之上提供真正的图遍历查询能力。

### 架构

```
摄取（processor.py）
  │
  ├─→ GraphExtractor（LLM 抽取）→ SQLite Entity/Relationship 表（兼容层）
  │
  └─→ LightRAG ainsert() → 独立存储（JSON / PostgreSQL）
                              ├── NetworkX 图（BFS 遍历）
                              ├── NanoVectorDB 向量索引
                              └── KV 文档存储
```

### 环境变量（独立配置）

```bash
# LLM（实体抽取 + 问答合成，可与 Embedding 不同 Provider）
LIGHTRAG_LLM_API_KEY=sk-...       # fallback: OPENAI_API_KEY
LIGHTRAG_LLM_API_BASE=...         # fallback: OPENAI_API_BASE
LIGHTRAG_LLM_MODEL=deepseek-chat  # fallback: EXTRACTION_MODEL

# Embedding（向量索引，定下来后不要随意更换）
LIGHTRAG_EMBED_API_KEY=AIzaSy...  # fallback: OPENAI_API_KEY
LIGHTRAG_EMBED_API_BASE=...       # fallback: OPENAI_API_BASE
LIGHTRAG_EMBED_MODEL=text-embedding-004  # fallback: EMBEDDING_MODEL
LIGHTRAG_EMBED_DIM=768            # 自动从已知模型推断，也可手动指定

# 存储后端
LIGHTRAG_STORAGE=json             # json（默认）| postgres
LIGHTRAG_PG_URL=postgresql://...  # storage=postgres 时需要
```

### 查询模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `naive` | 纯向量检索 | 简单问答 |
| `local` | 实体为中心的图检索 | "什么是 X" |
| `global` | 关系为中心的图检索 | "主题趋势是什么" |
| `hybrid` | local + global | 综合图问答 |
| `mix` | hybrid + 向量分块 | **最佳综合效果** |
| `bypass` | 不检索，直调 LLM | 测试 |

### 维度安全检测

当 `LIGHTRAG_EMBED_MODEL` 变更导致向量维度不一致时，LightRAG 会打印清晰错误提示，不会静默覆盖已有数据。用户需手动删除 `.softwiki/lightrag/` 或恢复配置。

---

## 五、尚未完成 / 下一步

### 5.1 index() 增量模式
- 当前 `index()` 是全量重建（delete all + recreate）
- `ingest()` 已支持单文档增量 append，但 `index()` 仍为全量
- 规划：`index()` 只处理 status=pending/indexed_stale 的文档

### 5.2 远程 MCP（Phase 2）
- 目前 MCP 只支持本地 stdio 模式
- 规划：支持 HTTPS + Bearer token 远程访问
- 拆分 `swshell` 独立客户端（零 core 依赖，通过 HTTP MCP 连远端）

### 5.3 Token / RBAC（Phase 3）
- 目前 mode 约束通过环境变量实现（honor system）
- 规划：正式 token 机制，每个 token 绑定 role + workspace 访问权限

### 5.4 其他
- `mcp` 包尚未从 pyproject.toml 列为正式依赖
- `ingestion/web_loader.py` BeautifulSoup 解析复杂页面效果有限
- WebUI 响应式布局优化

---

## 六、关键环境变量

```bash
# 工作空间
WORKSPACE_DIR=workspace/default

# Core LLM（抽取 / 问答 / Wiki 生成）
OPENAI_API_KEY=...
OPENAI_API_BASE=...
EXTRACTION_MODEL=gemini-2.5-flash
ANALYSIS_MODEL=gemini-2.5-flash

# Shell / TUI（独立，可与 Core 不同）
SHELL_MODEL=gemini-2.5-flash
SHELL_API_BASE=...
SHELL_API_KEY=...

# Embeddings
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# LightRAG（可选，见第四节）
LIGHTRAG_LLM_API_KEY=...
LIGHTRAG_LLM_API_BASE=...
LIGHTRAG_LLM_MODEL=...
LIGHTRAG_EMBED_API_KEY=...
LIGHTRAG_EMBED_API_BASE=...
LIGHTRAG_EMBED_MODEL=...
LIGHTRAG_EMBED_DIM=...
LIGHTRAG_STORAGE=json

# Web Search（BYOK，三选一）
TAVILY_API_KEY=...
SERPAPI_KEY=...
BING_SEARCH_API_KEY=...

# 运行模式
SOFTWIKI_MODE=wiki-admin           # wiki-admin / wiki-manage / wiki-work / wiki-study

# 功能开关
ENABLED_MODULES=rag,graph,claimdb,timeline,llmwiki
```

---

## 七、启动方式

```bash
# 安装依赖
pip install -e ".[dev,graph]"

# 复制并填写配置
cp .env.example .env

# 初始化默认工作空间
./sw init

# 摄入示例数据
python scripts/seed_eva.py

# 启动 Shell（需要 opencode 已安装）
./sw shell

# 启动 MCP server（供外部 AI 工具直接使用）
python -m softwiki.mcp.server

# 启动 REST API + WebUI
./sw api

# 导入 EVA 知识库到 LightRAG
WORKSPACE_DIR=workspace/eva-kb LIGHTRAG_LLM_API_KEY=... LIGHTRAG_EMBED_API_KEY=... python -c "
from softwiki.graph_rag.adapter import LightRAGAdapter
import asyncio
asyncio.run(LightRAGAdapter.get_instance().initialize())
"
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
