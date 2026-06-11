# Extension Points

> SoftWiki 的扩展能力设计：存储后端、模块开关、可选依赖与对外抽象边界。
>
> 相关文档：[架构概览](../01-architecture/overview.md) | [RAG 引擎](rag-engine.md) | [数据模型](data-model.md)

---

## 存储后端插件化

LightRAG 定义了 **4 种独立的存储类型**，每种类型支持多个可互换的后端实现：

| 存储类型 | 作用 | 可选后端 |
|----------|------|---------|
| **KV** | 关键值存储（LLM 缓存、元数据等） | `JsonKVStorage`（默认）、`PGKVStorage`、`RedisKVStorage` |
| **Vector** | 向量索引（实体/关系/文本块的 embedding） | `NanoVectorDBStorage`（默认）、`PGVectorStorage`、`QdrantStorage`、`MilvusStorage` |
| **Graph** | 知识图谱（实体-关系图） | `NetworkXStorage`（默认）、`PGGraphStorage`、`Neo4JStorage` |
| **Doc Status** | 文档处理状态追踪 | `JsonDocStatusStorage`（默认）、`PGDocStatusStorage` |

### 切换方式

存储后端的选择完全由环境变量驱动，**不需要修改代码**：

```python
# softwiki/graph_rag/adapter.py — _storage_config() + initialize()
backend = os.getenv("LIGHTRAG_STORAGE", "json")
```

- **`LIGHTRAG_STORAGE=json`**（默认）— 使用 JSON 文件 + NetworkX + NanoVectorDB，零外部依赖即可运行。
- **`LIGHTRAG_STORAGE=postgres`** — 使用 PostgreSQL 作为统一后端，需额外设置 `LIGHTRAG_PG_URL`。

PostgreSQL 模式下，KV、Vector、Graph、Doc Status 四种存储全部切换到对应的 PG 实现：

```python
# adapter.py initialize():
if store_cfg["backend"] == "postgres":
    from lightrag.kg.postgres_impl import (
        PGKVStorage, PGVectorStorage,
        PGGraphStorage, PGDocStatusStorage,
    )
    kv_storage = PGKVStorage
    vector_storage = PGVectorStorage
    graph_storage = PGGraphStorage
    doc_status_storage = PGDocStatusStorage
```

未来可类似方式接入 Redis（KV）、Qdrant / Milvus（向量）、Neo4J（图）等后端。

### 维度安全

切换 embedding 模型时，`_check_dimension_mismatch()` 检测既有向量索引的维度与新配置是否一致。不一致时阻断初始化并给出明确的修复指引（删除存储目录重新摄入，或回退配置）。**不会自动重建**，防止静默数据损坏。

---

## 模块开关

SoftWiki 的 5 个知识处理模块可通过 `ENABLED_MODULES` 环境变量独立启用/禁用：

| 模块标识 | 对应功能 | 默认状态 |
|----------|---------|---------|
| `rag` | 混合检索（Dense + BM25 + RRF） | 启用 |
| `graph` | 知识图谱（实体-关系抽取 + LightRAG） | 启用 |
| `claimdb` | 主张提取与查询 | 启用 |
| `timeline` | 时间线事件提取与查询 | 启用 |
| `llmwiki` | LLM Wiki 页面编译 | 启用 |

### 配置方式

```bash
export ENABLED_MODULES=rag,graph,claimdb,timeline,llmwiki   # 全部启用（默认）
export ENABLED_MODULES=rag,claimdb                           # 仅启用 rag 和 claimdb
export ENABLED_MODULES=                                      # 全部禁用
```

### 实现机制

`softwiki/config.py` 中的 `is_module_enabled()`：

```python
def is_module_enabled(module_name: str) -> bool:
    enabled_str = os.getenv("ENABLED_MODULES", "rag,graph,claimdb,timeline,llmwiki")
    enabled_list = [m.strip().lower() for m in enabled_str.split(",") if m.strip()]
    return module_name.strip().lower() in enabled_list
```

### 影响范围

所有提取和查询路径都尊重模块开关：

- **提取流水线**（`softwiki/extraction/processor.py`）：Claim、Graph、Timeline 三个提取器依次调用前检查 `is_module_enabled()`，禁用的模块直接跳过。
- **答案引擎**（`softwiki/intelligence/answer_engine.py`）：5 层上下文融合（RAG → ClaimDB → Graph → Timeline → LLM Wiki）各层独立检查 `is_module_enabled()`，禁用的层不参与检索和 LLM 合成。
- **API 层**（`softwiki/api/server.py`）：`/api/modules` 端点返回所有模块的启用状态。

### 组合示例

| 场景 | ENABLED_MODULES | 效果 |
|------|----------------|------|
| 纯 RAG 知识库 | `rag` | 仅做混合检索和问答，不抽取图谱/主张/事件 |
| 图谱增强研究 | `rag,graph,timeline` | 启用 RAG + 知识图谱 + 时间线，禁用主张和 Wiki |
| 轻量级声明追踪 | `claimdb` | 只做主张提取和查询，不加载向量索引和 LightRAG |

---

## 可选依赖

SoftWiki 通过 Python `[project.optional-dependencies]` 定义可选安装组：

```toml
# pyproject.toml
[project.optional-dependencies]
graph = [
    "lightrag-hku>=1.5.0",
]
dev = [
    "pytest>=7.0.0",
]
```

| Extra | 安装命令 | 包含依赖 | 用途 |
|-------|---------|---------|------|
| 基础 | `pip install softwiki` | fastapi, uvicorn, click, sqlalchemy, openai, numpy, ... | 核心功能（RAG、搜索、API） |
| `graph` | `pip install softwiki[graph]` | lightrag-hku | 知识图谱多跳推理（LightRAG） |
| `dev` | `pip install softwiki[dev]` | pytest | 开发和测试 |

```bash
# 典型安装
pip install softwiki[graph]   # 生产部署（含图谱能力）
pip install softwiki[dev]     # 开发环境
pip install softwiki[graph,dev]  # 全功能开发环境
```

### 设计原则

- `lightrag-hku` 作为可选依赖：LightRAG 体积较大且对部分场景非必需（如仅使用基础 RAG 的用户），故放于 `graph` extra 中按需安装。
- 运行时通过 `has_lightrag_credentials()`（`adapter.py`）检测 credential 是否就绪，未就绪时 LightRAG 相关功能静默降级，不抛出导入错误。
- `dev` extra 包含测试工具链，不包含 mock 库等第三方测试辅助——保持最小化。

---

## 对外抽象边界

### MCP 是唯一能力边界

MCP（Model Context Protocol）是 SoftWiki 对外的**正式且唯一的能力边界**。所有外部工具通过 MCP 协议（stdio JSON-RPC）与 SoftWiki 交互：

```
外部 AI 工具        控制流              SoftWiki
─────────────    ──────────          ──────────
opencode           ──── MCP ────▶    MCP Server → Core
Claude Desktop     ──── MCP ────▶    MCP Server → Core
Cursor             ──── MCP ────▶    MCP Server → Core
自定义 Agent       ──── MCP ────▶    MCP Server → Core
WebUI (Next.js)    ──── REST ───▶    API Server → Core
Shell TUI          ──── MCP ────▶    MCP Server → Core
```

### 核心约束

1. **Core 零外部依赖** — Core 层（ingestion、extraction、intelligence、source_store、rag、wiki 等）的**所有功能可以通过 CLI 直接使用**，不依赖任何外部 AI 工具（opencode、Claude、Cursor 等）。

2. **Shell TUI 通过 MCP 调用 Core** — `./sw shell` 启动的交互式 TUI 内部通过 MCP stdio 子进程与 Core 通信，**不直接 import Core 模块**。这强制了统一的能力边界。

3. **WebUI 通过 REST API 调用** — Next.js 前端只消费 `softwiki/api/server.py` 暴露的 FastAPI 端点，不直接访问 Python 内部 API。

4. **MCP Server 可独立运行** — `python -m softwiki.mcp.server` 作为独立 stdio 进程运行，可注册到任何 MCP 主机（Claude Desktop、opencode、Cursor 等）的配置中。

### 扩展方式

| 扩展目标 | 方式 | 示例 |
|---------|------|------|
| 新增 MCP tool | 在 `softwiki/mcp/server.py` 添加 `@mcp.tool()` 函数 | `@mcp.tool() async def custom_query(...)` |
| 新增 REST endpoint | 在 `softwiki/api/server.py` 添加 FastAPI router | `@router.post("/api/custom")` |
| 新增 CLI 命令 | 在 `softwiki/cli/main.py` 添加 Click group | `@cli.command() def export(): ...` |
| 新增存储后端 | 实现 LightRAG 对应的 Storage 接口 + 环境变量派发分支 | 参见 `adapter.py initialize()` 的 backend switch |
| 新增知识模块 | 在 extraction 中添加新的 Extractor + 在 answer_engine 中添加新的 context layer | 复用 `is_module_enabled()` 守卫 |

### 不允许的扩展

- **Core 直接 import 外部工具** — 不可在 Core 中 import opencode、claude 等 SDK。
- **绕过 MCP 的能力暴露** — 所有外部可编程入口必须通过 MCP 或 REST API，不开放仅 Python 内部函数暴露给外部 Agent。

---

## 总结

| 扩展维度 | 机制 | 配置点 | 影响范围 |
|---------|------|-------|---------|
| 存储后端 | LightRAG Storage 接口 + 环境变量 | `LIGHTRAG_STORAGE` / `LIGHTRAG_PG_URL` | KV、Vector、Graph、Doc Status 四类存储 |
| 模块开关 | `is_module_enabled()` + `ENABLED_MODULES` | 环境变量 | 提取流水线、答案引擎 5 层上下文 |
| 可选依赖 | `pyproject.toml` extras | pip install | graph、dev 两组依赖 |
| 对外边界 | MCP / REST / CLI | — | 所有外部交互必须通过三层接口之一 |
