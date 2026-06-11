# Extraction Pipeline

## 五阶段管道

SoftWiki 将文档从原始来源到结构化知识的转化拆解为五个串行阶段，每个阶段有明确的输入/输出和落盘位置。

### 1. 摄取 (ingestion)

**入口**: `softwiki/ingestion/web_loader.py` / `pdf_loader.py`

| 输入 | 处理 | 输出 |
|------|------|------|
| URL 或本地 PDF 路径 | requests + BeautifulSoup 抓取网页，或 PyMuPDF 提取 PDF 文本 | raw_text + cleaned_text + metadata(title, author, published_at, language) |

**落盘**: `raw/html/<url_hash>.html`（网页原始 HTML）或 `raw/pdf/<doc_id>_<filename>.pdf`（PDF 副本）

**DB**: `Document` 记录写入 processed.db（raw_text、cleaned_text、hash、published_at 等字段）。

**去重**: `calculate_hash()` 对 cleaned_text 取 SHA256 哈希，`is_duplicate_hash()` / `is_duplicate_url()` 在 insert 前检查；命中则跳过。

**范围守卫**: `check_scope()` 用 LLM 判断内容是否在工作区 scope.md 定义的主题范围内，out-of-scope 直接跳过。

### 2. 清洗 (normalize)

**入口**: `softwiki/ingestion/normalize.py`

| 输入 | 处理 | 输出 |
|------|------|------|
| 上一阶段的 raw_text | `normalize_text()` → `clean_whitespace()`（合并连续换行/空格）→ 智能引号/破折号转为 ASCII | 干净的纯文本 |

**落盘**: `.softwiki/md/<doc_id>_<slug>.md` — 带元数据头部的 markdown 文件（标题、来源、语言、URL、日期）。

```
doc_id    : 42
title     : Some Article Title
language  : en
source    : Reuters
url       : https://...
date      : 2025-06-01
============================================================

[cleaned text body...]
```

**说明**: web_loader/pdf_loader 内部已调用 normalize_text，所以 cleaned_text 本身已清洗。本阶段指 `save_processed_document()` 将清洗文本单独落盘，使中间结果可检视。

### 3. 分块 (chunking)

**入口**: `softwiki/rag/chunker.py`

| 输入 | 处理 | 输出 |
|------|------|------|
| cleaned_text + metadata | `build_document_chunks()` → 段落感知切割，支持 section 追踪，chunk_size=1000，overlap=200 | 带上下文 header 的结构化 chunk 列表 |

每个 chunk 包含:
- `document_id`, `chunk_index`, `text`（含 `[Document: ... | Source: ... | Date: ... | Section: ...]` header）
- `title`, `section`, `published_at`

**落盘**: `.softwiki/chunks/<doc_id>.json` — 全部 chunk 的 JSON 数组。

**DB**: `Chunk` 记录写入 processed.db。

**向量/BM25 增量**:
- `LocalVectorStore.add_vectors(chunk_ids, embeddings)` — 逐文档 append 到 `.softwiki/index/vector_index.npz`
- `Bm25Store.add_documents({cid: text})` — 追加到 `.softwiki/index/bm25_index.pkl` 并内部 rebuild（BM25 需要全语料 IDF）

### 4. 抽取 (extraction)

**入口**: `softwiki/extraction/processor.py`

| 输入 | 处理 | 输出 |
|------|------|------|
| cleaned_text[:15000] + doc_id + published_at | 按模块配置依次运行三个抽取器：Claim → Graph → Timeline | 结构化知识记录写入 DB |

**三个子模块**（通过 `ENABLED_MODULES` 环境变量控制，默认全部开启）:

1. **Claim DB** — `ClaimExtractor.extract_claims()` → LLM 从文本中提取主张（actor、topic、stance、confidence）→ `DocumentRepository.create_claim()`
2. **Graph** — `GraphExtractor.extract_graph()` → LLM 提取实体和关系
   - 实体（name, type, description）→ `create_entity()`
   - 关系（source→target, relation_type, confidence）→ `create_relationship()`
   - 可选：同步插入 LightRAG（`LightRAGAdapter.sync_insert_text()`）
3. **Timeline** — `TimelineExtractor.extract_events()` → LLM 提取时间线事件（title, description, event_date, topic）→ `create_event()`

**状态流转**: `pending → extracting → completed | failed`

### 5. 落盘 (file_store)

**入口**: `softwiki/ingestion/file_store.py`

抽取完成后，将 DB 中的结构化结果序列化为 JSON，落盘到 `.softwiki/extractions/<doc_id>.json`，格式:

```json
{
  "doc_id": 42,
  "claims": [{ "actor": "...", "topic": "...", "stance": "...", ... }],
  "entities": [{ "name": "...", "type": "...", "description": "..." }],
  "relationships": [{ "source": "...", "target": "...", "relation": "...", ... }],
  "events": [{ "title": "...", "description": "...", "event_date": "...", ... }]
}
```

**说明**: DB 是唯一真相源（source of truth），磁盘文件仅用于管道可观测性和外部工具检视。`save_extraction()` 失败不会中断管道。

---

## 同步 vs 异步

`run_extraction_pipeline(db, doc_id, cleaned_text, published_at, background=False)` 通过 `background` 参数切换模式:

| 模式 | 行为 | 使用场景 |
|------|------|---------|
| `background=False`（默认） | 当前线程同步执行全部三个抽取模块，等待完成，返回结果 dict | `softwiki ingest --url ...` CLI |
| `background=True` | 设置 doc.status = "pending"，派发 daemon 线程，立即返回占位结果 | REST API (`/api/ingest/*`)、MCP `ingest()` |

### 后台线程细节

```python
t = threading.Thread(target=_bg_extraction_worker, args=(doc_id, cleaned_text, published_at))
t.daemon = True
t.start()
```

- 线程内创建独立的 SQLAlchemy session（`SessionLocal()`），避免与父事务冲突
- **`time.sleep(0.5)`** — 短暂延迟确保父事务（Document insert + commit）在子线程读取前完成
- 线程内捕获所有异常，失败时设置 doc.status = "failed"
- daemon 线程不阻止进程退出

### 调用链

```
CLI:   ingest → run_extraction_pipeline(background=False) → 同步等待 → 输出结果
API:   ingest_url/file → run_extraction_pipeline(background=True) → 返回 {"extraction": "pending"}
MCP:   ingest() → Stage 1-3 同步执行 → Stage 4 后台派发 → 返回摘要
```

---

## 增量策略

### 摄取即索引 (ingest-time indexing)

MCP `ingest()` 在摄取阶段即完成分块和索引更新，无需手动调用 `index()`:

1. `build_document_chunks()` → 生成 chunk
2. `save_chunks()` → 落盘 `.softwiki/chunks/<doc_id>.json`
3. `create_chunks()` → DB 写入
4. `embed_texts()` → 生成向量
5. `LocalVectorStore.add_vectors()` → append 到 `.softwiki/index/vector_index.npz`
6. `Bm25Store.add_documents()` → append 到 `.softwiki/index/bm25_index.pkl`

BM25 由于算法需要全语料 IDF，`add_documents()` 内部会执行全量 rebuild（而非真增量），但对外表现为增量追加。

### 异步 LLM 抽取

LLM 抽取（Stage 4）由后台 daemon 线程异步执行，不阻塞用户操作。用户发起 ingest 后立即获得响应，抽取结果最终写入 DB 和 `.softwiki/extractions/`。

### LightRAG 增量插入

`LightRAGAdapter.sync_insert_text()` 调用 `LightRAG.ainsert()`—LightRAG 内部按文档粒度进行:
1. 文本重新分块
2. LLM 抽取实体和关系
3. 按实体名 merge 节点/边（incremental graph building）
4. 更新向量索引

同一来源文档的增量插入不会产生重复节点（由 LightRAG 的 graph merge 逻辑保证）。

### index() 命令

`softwiki index` CLI 命令目前为**全量重建**:
1. 删除所有 chunk（`delete_document_chunks()`）
2. 对所有文档重新分块
3. 删除旧向量/BM25 索引文件并重建

> **规划**: 后续版本将支持增量 index() 模式，仅处理自上次索引后新增/变更的文档。

### 全链路状态机

```
ingestion
   │
   ▼
normalize ──► .softwiki/md/
   │
   ▼
chunking ──► .softwiki/chunks/ + vector/BM25 append
   │
   ├── [background=False] ──► synchronous extraction ──► completed
   └── [background=True]  ──► pending → [daemon thread] → extracting → completed|failed
                                    │
                                    ▼
                              .softwiki/extractions/
```

---

## Pipeline 文件落盘结构

```
workspace/<ws>/
├── raw/
│   ├── html/<url_hash>.html        ← Stage 1: 原始网页 HTML
│   └── pdf/<doc_id>_<filename>.pdf ← Stage 1: PDF 副本
├── .softwiki/
│   ├── md/<doc_id>_<slug>.md       ← Stage 2: 清洗后文本
│   ├── chunks/<doc_id>.json        ← Stage 3: 分块结果
│   ├── extractions/<doc_id>.json   ← Stage 4→5: 抽取结果（claims/entities/relationships/events）
│   └── index/                      ← Stage 3: 搜索索引
│       ├── vector_index.npz        ←   FAISS-flat 向量索引（numpy .npz）
│       └── bm25_index.pkl          ←   BM25 关键词索引（pickle）
└── exports/wiki/                   ← Wiki 页面构建输出（wiki build 命令）
```

| 目录 | 对应阶段 | 格式 | 写入时机 | 是否真相源 |
|------|---------|------|---------|-----------|
| `raw/` | 1 摄取 | HTML / PDF | ingest 时 | ❌ |
| `.softwiki/md/` | 2 清洗 | Markdown | ingest 时 | ❌ |
| `.softwiki/chunks/` | 3 分块 | JSON | ingest / index 时 | ❌ |
| `.softwiki/extractions/` | 4→5 抽取 | JSON | extraction 完成后 | ❌ |
| `.softwiki/index/` | 3 索引 | .npz / .pkl | ingest / index 时 | ❌（可重建） |
| `processed.db` | 全部 | SQLite | 各阶段持续写入 | ✅ |
| `exports/wiki/` | 编译 | Markdown | wiki build 时 | ❌ |

DB（processed.db）是唯一真相源，磁盘文件均为辅助检视和调试用途。
