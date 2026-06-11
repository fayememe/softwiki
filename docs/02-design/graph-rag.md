# Graph-RAG Design

## 双轨架构

SoftWiki 维护两条并行的图存储轨道，服务于不同查询深度：

| 轨道 | 组件 | 存储 | 查询方式 | 适用场景 |
|------|------|------|---------|---------|
| SQLite 兼容层 | `GraphExtractor` → `Entity`/`Relationship` 表 | SQLite (`processed.db`) | `SQL LIKE` 模糊匹配 | 轻量关键词过滤，无图遍历需求 |
| LightRAG 增强层 | `LightRAGAdapter` → `LightRAG` | 独立存储（JSON/PostgreSQL） | 6 种向量 + 图查询模式 + BFS 子图遍历 | 多跳推理、实体为中心问答、关系趋势分析 |

两条轨道各自独立存储，互不依赖。LightRAG 增强层通过 `has_lightrag_credentials()` 检查凭据是否可用，**降级友好**：凭据未配置时 SQLite 层仍可正常工作。

---

## SQLite 兼容层

### 入口

`softwiki/extraction/graph_extractor.py` → `GraphExtractor.extract_graph()`

### 存储模型

**Entity 表**（`softwiki/source_store/models.Entity`）:

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | Integer | PK, autoincrement |
| `name` | String(150) | **UNIQUE, NOT NULL** — upsert 合并依据 |
| `type` | String(100) | person / organization / country / concept / location / project |
| `description` | Text | 可为空 |

**Relationship 表**（`softwiki/source_store/models.Relationship`）:

| 列 | 类型 | 约束 |
|----|------|------|
| `id` | Integer | PK, autoincrement |
| `source_name` | String(150) | NOT NULL |
| `target_name` | String(150) | NOT NULL |
| `relation_type` | String(100) | NOT NULL |
| `description` | Text | 可为空 |
| `document_id` | Integer | FK → `documents.id` ON DELETE CASCADE |
| `confidence` | Float | default 1.0 |
| `published_at` | DateTime | 可为空 |

### 写入逻辑

**Entity**: `name` 字段 unique 约束，重复时 **upsert**（先查后更新 description/type）。由 `DocumentRepository.create_entity()` 实现。

**Relationship**: **blind insert** — 每次抽取直接 INSERT，不做去重。同一对实体间可能存在多条来自不同文档的关系记录。document_id 作为外键关联回 Document 表。

### 抽取流程

```
cleaned_text
    │
    ├── [LLM 可用] LLM 抽取 ──► JSON parse ──► Entity / Relationship 对象列表
    │
    └── [LLM 不可用] _fallback_extract_graph()
                │
                ├── 正则提取大写首字母词汇（过滤介词/冠词）
                ├── 取前 7 个去重候选作为 Entity（type="concept"）
                └── Co-occurrence 关系规则 ──► Relationship（type="associated_with" / "disputes_with" / "member_of"）
```

LLM 抽取优先，失败时自动降级到启发式规则（`_fallback_extract_graph`）。

### 查询方式

仅支持 **SQL `LIKE`** 过滤，无图遍历能力：

```sql
-- 按描述关键词过滤关系
SELECT * FROM relationships
WHERE description LIKE '%keyword%'
   OR source_name LIKE '%keyword%'
   OR target_name LIKE '%keyword%';
```

由 `AnswerEngine.ask()` 的 Layer 3 (Graph) 模块调用。先尝试 LightRAG 查询，**降级回退**到 SQL LIKE。

---

## LightRAG 增强层

### 入口

`softwiki/graph_rag/adapter.py` → `LightRAGAdapter`

### 初始化

```python
adapter = LightRAGAdapter.get_instance(workspace_dir)
await adapter.initialize()
```

单例模式（per workspace），`get_instance()` 返回同 workdir 的共享实例。

### 增量插入

```
ainsert(text)
    │
    ├── 1. 文本分块（chunk_token_size=1200, overlap=100）
    ├── 2. LLM 自动抽取实体 + 关系
    ├── 3. 按实体名 merge 节点/边（incremental graph building）
    ├── 4. 计算 embedding（NanoVectorDB / PGVectorStorage）
    └── 5. 更新图存储（NetworkX / PGGraphStorage）
```

由 `LightRAG.ainsert()` 原生实现。同一来源文档的增量插入不会产生重复节点（graph merge 按实体名去重）。

`source_id` 会以 `[Source: <id>]\n` 前缀 prepend 到文本中，保留来源追踪。

### 6 种查询模式

通过 `LightRAGAdapter.query(question, mode)` 的 `mode` 参数选择：

| 模式 | 检索策略 | 适用场景 | 实现方式 |
|------|---------|---------|---------|
| `naive` | 纯向量检索（无图遍历） | 简单问答，无需实体关系推理 | 直接向量相似度 top-k |
| `local` | 以实体为中心，检索该实体的邻域子图 | "什么是 X"、"X 的特征是什么" | 实体 embedding → 邻接边/节点 |
| `global` | 以关系为中心，跨实体聚合 | 主题趋势、"各组织对 X 的立场" | 关系 embedding → 全局聚合 |
| `hybrid` | local + global 联合检索 | 综合图问答 | 两路分别检索后合并 |
| `mix` | hybrid + 向量分块上下文 | 需要最佳效果的场景 | hybrid + chunk 向量检索融合 |
| `bypass` | 不检索，直接调用 LLM | 测试、元问答 | context 为空，纯 LLM 回答 |

默认模式为 `mix`，`top_k` 默认 40。

**额外工具** — `query_context(question, mode)`：获取检索到的原始上下文（不经过 LLM 合成），适用于调试或外部处理。

### BFS 子图遍历

```
LightRAGAdapter.explore(entity_name, max_depth=2, max_nodes=50)
    │
    └── graph_storage.get_knowledge_graph(entity, max_depth, max_nodes)
                │
                └── BFS 从 {entity} 出发，逐层扩展邻接节点，到 max_depth 层为止
```

返回结构化 dict：

```json
{
  "entity": "EntityName",
  "max_depth": 2,
  "nodes_count": 15,
  "edges_count": 23,
  "nodes": [
    {"id": "...", "labels": ["Entity", "Organization"], "properties": {...}},
    ...
  ],
  "edges": [
    {"id": "...", "type": "cooperates_with", "source": "...", "target": "...", "properties": {...}},
    ...
  ],
  "is_truncated": false
}
```

`is_truncated` 标记 max_nodes 限制是否截断了结果。用于前端提示用户可缩小查询范围或增加限制。

### 同步包装器

为 MCP 工具等非 async 上下文提供 sync 接口：

| 异步 | 同步 |
|------|------|
| `insert_text()` | `sync_insert_text()` |
| `query()` | `sync_query()` |
| `query_context()` | `sync_query_context()` |
| `explore()` | `sync_explore()` |
| `get_status()` | `sync_get_status()` |

同步包装器通过 `asyncio.new_event_loop()` + `run_until_complete()` 实现，兼容已有 running loop 或新建 loop 两种场景。

---

## 存储后端

### 默认后端：JSON（零配置）

| 存储组件 | 实现 | 落盘文件 |
|---------|------|---------|
| KV Storage | `JsonKVStorage` | `kv_store.json` |
| Vector Storage | `NanoVectorDBStorage` | `vdb_entities.json`, `vdb_relationships.json`, `vdb_chunks.json` |
| Graph Storage | `NetworkXStorage` | `graph_chunk_entity_relation.graphml` |
| Doc Status | `JsonDocStatusStorage` | `doc_status.json` |

存储位置：`<workspace>/.softwiki/lightrag/`（由 `get_softwiki_dir("lightrag")` 解析）。

### PostgreSQL 后端

| 存储组件 | 实现类 |
|---------|--------|
| KV Storage | `PGKVStorage` |
| Vector Storage | `PGVectorStorage` |
| Graph Storage | `PGGraphStorage` |
| Doc Status | `PGDocStatusStorage` |

### 配置方式

```bash
# 默认 JSON（无需配置）
export LIGHTRAG_STORAGE=json

# PostgreSQL
export LIGHTRAG_STORAGE=postgres
export LIGHTRAG_PG_URL=postgresql://user:pass@localhost:5432/softwiki
```

---

## 维度安全

当 embedding 模型变更导致向量维度不一致时，LightRAG 无法继续使用既有索引。

### 检查机制

`_check_dimension_mismatch()` 在 `initialize()` 时执行：

1. 检查 `graph_chunk_entity_relation.graphml` 是否存在（判断是否为已有数据的工作区）
2. 读取 NanoVectorDB 存储文件中记录的 `embedding_dim`（`vdb_entities.json` / `vdb_relationships.json` / `vdb_chunks.json`）
3. 与当前配置的 `LIGHTRAG_EMBED_DIM` 或 `KNOWN_EMBED_DIMS[model]` 比较
4. 不一致时打印醒目错误信息（box-drawing 边框）并抛出 `RuntimeError`

### 已知模型维度表

`KNOWN_EMBED_DIMS` 字典内建常见模型维度映射：

| 模型 | 维度 |
|------|------|
| `text-embedding-3-small` | 1536 |
| `text-embedding-3-large` | 3072 |
| `text-embedding-ada-002` | 1536 |
| `text-embedding-004` | 768 |
| `models/embedding-001` | 768 |
| `deepseek-embedding` | 2048 |
| `bge-m3` | 1024 |
| `bge-small-zh-v1.5` | 512 |
| `all-MiniLM-L6-v2` | 384 |

未在表中的模型默认 `1536`（OpenAI 兼容），可通过 `LIGHTRAG_EMBED_DIM` 环境变量显式覆盖。

### 修复方式

```
# 删除 LightRAG 存储目录，重新摄入所有文档
rm -rf <workspace>/.softwiki/lightrag/
```

**永不自动重建** — 用户必须显式删除或回退配置，避免数据静默损坏。

---

## LLM / Embedding 分离

LLM（实体抽取 + 查询合成）和 Embedding（向量索引）使用**完全独立的配置项**，可指向不同 provider：

### LLM 配置

| 环境变量 | 回退 | 默认值 |
|---------|------|--------|
| `LIGHTRAG_LLM_API_KEY` | `OPENAI_API_KEY` | `""` |
| `LIGHTRAG_LLM_API_BASE` | `OPENAI_API_BASE` | `https://api.openai.com/v1` |
| `LIGHTRAG_LLM_MODEL` | `EXTRACTION_MODEL` | `gpt-4o-mini` |

### Embedding 配置

| 环境变量 | 回退 | 默认值 |
|---------|------|--------|
| `LIGHTRAG_EMBED_API_KEY` | `OPENAI_API_KEY` | `""` |
| `LIGHTRAG_EMBED_API_BASE` | `OPENAI_API_BASE` | `https://api.openai.com/v1` |
| `LIGHTRAG_EMBED_MODEL` | `EMBEDDING_MODEL` | `text-embedding-3-small` |
| `LIGHTRAG_EMBED_PROVIDER` | `EMBEDDING_PROVIDER` | `openai` |
| `LIGHTRAG_EMBED_DIM` | `KNOWN_EMBED_DIMS[model]` | `1536` |

### 分离示例

```bash
# LLM 用 OpenAI
export LIGHTRAG_LLM_API_KEY=sk-xxx
export LIGHTRAG_LLM_MODEL=gpt-4o

# Embedding 用本地模型
export LIGHTRAG_EMBED_PROVIDER=local
export LIGHTRAG_EMBED_DIM=384
```

### Local Embedding Provider

`provider=local` 时使用基于字符哈希的零依赖 embedding：

```python
# 将 UTF-32 字符编码值取模映射到 dim 空间
chars = np.frombuffer(text.encode("utf-32", "replace"), dtype=np.uint32)[1:] % dim
embed = np.bincount(chars, minlength=dim).astype(np.float32)
embed = embed / (np.linalg.norm(embed) + 1e-12)
```

无需 API 密钥即可生成确定性向量，适合开发测试或纯本地场景。

---

## 凭据检查

`has_lightrag_credentials()` 控制整层是否激活：

```python
def has_lightrag_credentials() -> bool:
    llm = _llm_config()
    emb = _embed_config()
    llm_ok = bool(llm["api_key"]) and not llm["api_key"].startswith("your_")
    emb_ok = bool(emb["api_key"]) and not emb["api_key"].startswith("your_") or emb["provider"] == "local"
    return llm_ok and emb_ok
```

- `local` provider 不需要 API key（emb_ok = True）
- 占位符 `your_*` 开头的 key 视为未配置
- 凭据不足时 `LightRAGAdapter.get_instance()` 仍可创建，但 `initialize()` 时的 LLM/Embedding 调用会失败

---

## 状态监控

`get_status()` 返回 LightRAG 存储状态：

```json
{
  "initialized": true,
  "working_dir": "/path/to/.softwiki/lightrag",
  "graph_nodes": 1423,
  "graph_edges": 5782,
  "graph_error": null
}
```

用于健康检查和运维监控。graph_nodes/graph_edges 直接读取 NetworkX 图计数。
