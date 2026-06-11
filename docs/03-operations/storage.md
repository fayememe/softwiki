# 存储架构

> **范围**: SoftWiki 所有存储层的布局与配置：工作区文件系统、SQLite 数据库、LightRAG 存储及 PostgreSQL 可选后端。
> **适用对象**: 需要理解数据落盘位置与存储结构的操作人员。

---

## Workspace 文件系统

每个工作区（workspace）是一个独立目录，包含其所有数据、配置和输出。路径由 `WORKSPACE_DIR` 环境变量控制，默认为 `workspace/default`。

```
workspace/<name>/
├── raw/                        # 原始文件
│   ├── html/                   #   原始 HTML（fetched）
│   ├── pdf/                    #   原始 PDF（copy）
│   ├── markdown/               #   原始 Markdown
│   └── api/                    #   API 响应快照
│
├── .softwiki/                  # SoftWiki 内部数据
│   ├── processed.db            #   SQLite 数据库（主存储）
│   ├── md/                     #   清洗后文本（.md，可人工阅读）
│   ├── chunks/                 #   分块 JSON（每文档一个文件）
│   ├── extractions/            #   LLM 抽取结果（claims/entities/relationships/events）
│   ├── documents/              #   文档中间数据
│   ├── embeddings/             #   嵌入向量缓存
│   ├── index/                  #   搜索索引（FAISS 向量 + BM25 关键词）
│   └── lightrag/               #   LightRAG 独立存储（见下文）
│
├── config/                     # 工作区配置
│   ├── sources.yaml            #   数据源定义
│   ├── model_profiles.yaml     #   LLM 模型配置
│   ├── scope.md                #   研究范围定义
│   ├── agents.md               #   自定义 agent soul（可选）
│   └── workflows.yaml          #   自定义 workflow 覆盖（可选）
│
├── exports/                    # 导出输出
│   └── wiki/                   #   Wiki 页面输出
│       ├── countries/
│       ├── organizations/
│       ├── topics/
│       ├── events/
│       ├── claims/
│       └── reports/
│
└── .softwiki.yml               # 工作区元数据（可选）
```

> **注意**: `raw/` 和 `.softwiki/` 中的管道产物只作为检查点供人工审查，**不是数据真相源**。所有持久化数据的权威来源是 `.softwiki/processed.db`。

---

## SQLite

### 数据库

- **路径**: `{WORKSPACE_DIR}/.softwiki/processed.db`
- **连接 URL**（SQLAlchemy）: `sqlite:///{WORKSPACE_DIR}/.softwiki/processed.db`
- **ORM**: SQLAlchemy（`softwiki/source_store/db.py` 中的 `Base`）

### 表

| 表名 | 模型类 | 用途 |
|------|--------|------|
| `sources` | `SourceConfig` | 预定义数据源配置（名称、类型、URL、信任级别） |
| `documents` | `Document` |  ingested 文档元数据与全文（title, url, raw_text, cleaned_text, hash） |
| `chunks` | `Chunk` | 文档分块（text, section, chunk_index），外键 → documents |
| `claims` | `Claim` | LLM 抽取的声明（actor, topic, stance, confidence），外键 → documents |
| `entities` | `Entity` | 知识图谱实体（name, type, description），全局唯一 |
| `relationships` | `Relationship` | 实体间关系（source_name, target_name, relation_type），外键 → documents |
| `events` | `Event` | 时间线事件（title, event_date, topic），外键 → documents |

### 初始化

数据库表在 `softwiki init` 时自动创建。SQLite 文件由 `get_db_url()` 在第一次访问时自动创建目录并返回连接字符串。

---

## LightRAG JSON 存储

LightRAG 有自己独立的数据存储，运行在 SQLite 体系之外。默认使用基于 JSON 文件的后端，不需要额外基础设施。

### 目录

```
{WORKSPACE_DIR}/.softwiki/lightrag/
├── graph_chunk_entity_relation.graphml   # NetworkX 图结构（XML）
├── vdb_entities.json                     # 实体向量（NanoVectorDB）
├── vdb_relationships.json                # 关系向量（NanoVectorDB）
├── vdb_chunks.json                       # 分块向量（NanoVectorDB）
├── kv_store_full_docs.json               # 完整文档 KV 元数据
├── kv_store_text_chunks.json             # 文本分块 KV 元数据
├── kv_store_llm_response_cache.json      # LLM 响应缓存（KV）
└── kv_store_entity_meta.json             # 实体元数据（KV）
```

### 文件说明

| 文件 | 存储后端 | 格式 | 内容 |
|------|----------|------|------|
| `*graphml` | NetworkXStorage | GraphML (XML) | 节点（实体）+ 边（关系）的图拓扑 |
| `vdb_*.json` | NanoVectorDBStorage | JSON | embedding vectors + 元数据；每文件含 `embedding_dim` |
| `kv_store_*.json` | JsonKVStorage / JsonDocStatusStorage | JSON | 纯键值元数据、文档状态、LLM 缓存 |

### 维度一致性检查

LightRAG 启动时校验当前配置的 embedding 维度是否与现有 NanoVectorDB 文件中的 `embedding_dim` 一致。若不匹配则拒绝启动并提示用户删除 `.softwiki/lightrag/` 目录后重新 ingest。

---

## PostgreSQL

### 适用场景

当工作区数据规模或并发访问需求超出 SQLite + JSON 文件的承载能力时，可切换 LightRAG 存储至 PostgreSQL。

### 配置

| 环境变量 | 值 |
|----------|-----|
| `LIGHTRAG_STORAGE` | `postgres` |
| `LIGHTRAG_PG_URL` | `postgresql://user:pass@host:5432/softwiki` |

### 后端映射

当 `LIGHTRAG_STORAGE=postgres` 时，LightRAG 自动使用以下 PostgreSQL 实现：

| 抽象层 | JSON 默认实现 | PostgreSQL 实现 |
|--------|--------------|-----------------|
| KV 存储 | `JsonKVStorage` | `PGKVStorage` |
| 向量存储 | `NanoVectorDBStorage` | `PGVectorStorage` |
| 图存储 | `NetworkXStorage` | `PGGraphStorage` |
| 文档状态 | `JsonDocStatusStorage` | `PGDocStatusStorage` |

### 系统依赖

使用 PostgreSQL 后端需要安装：

- **Python**: `asyncpg`（异步 PostgreSQL 驱动）
- **PostgreSQL**: `pgvector` 扩展（向量相似性搜索）

```bash
# Python 依赖
pip install asyncpg

# PostgreSQL 扩展
CREATE EXTENSION vector;
```

### 注意事项

- PostgreSQL 仅作用于 **LightRAG 层**。主数据（documents、chunks、claims 等）仍存储在 SQLite 中。
- 切换存储后端后，现有 JSON 存储中的数据**不会自动迁移**。需重新 ingest。
