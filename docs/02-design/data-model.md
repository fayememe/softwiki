# 数据模型

> 设计级参考：SoftWiki 中所有核心数据模型、字段、关系与生命周期。
>
> 相关文档：[RAG 引擎](rag-engine.md) | [提取流水线](pipeline.md)

---

## 核心模型

共 7 个 SQLAlchemy ORM 模型，均定义在 `softwiki/source_store/models.py` 中，使用 `declarative_base()`。

---

### 1. SourceConfig

**表名：** `sources`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `String(100)` | PK | 来源标识 |
| `name` | `String(200)` | NOT NULL | 来源名称 |
| `type` | `String(50)` | | 来源类型：`official`, `news`, `think_tank`, `academic` 等 |
| `url` | `String(500)` | | 来源 URL |
| `trust_level` | `String(50)` | | 信任等级：`high`, `medium`, `low` |
| `source_country` | `String(100)` | | 来源国家/地区 |
| `language` | `String(10)` | | 语言代码（如 `zh`, `en`） |

SourceConfig 为独立配置表，不通过外键与 Document 直接关联；文档通过 `source_name` 字段与来源名称进行软关联。

---

### 2. Document

**表名：** `documents`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `Integer` | PK, autoincrement | 文档 ID |
| `title` | `String(500)` | NOT NULL | 文档标题 |
| `url` | `String(1000)` | | 原始 URL |
| `source_name` | `String(200)` | | 来源名称（与 SourceConfig.name 做软关联） |
| `source_type` | `String(100)` | | 来源类型快照 |
| `source_country` | `String(100)` | | 来源国家快照 |
| `published_at` | `DateTime` | | 原文发布时间 |
| `collected_at` | `DateTime` | 默认 `utcnow` | 采集时间 |
| `language` | `String(50)` | | 文档语言 |
| `author` | `String(200)` | | 作者 |
| `raw_text` | `Text` | NOT NULL | 原始文本（抓取原文） |
| `cleaned_text` | `Text` | NOT NULL | 清洗后文本（去噪、标准化） |
| `hash` | `String(64)` | **UNIQUE**, NOT NULL | 内容哈希，用于去重 |
| `trust_level` | `String(50)` | | 继承自来源的信任等级 |
| `topics` | `String(500)` | | 逗号分隔的话题标签 |
| `status` | `String(50)` | 默认 `completed` | 处理状态（见生命周期） |

**级联关系：** Document 通过 `cascade="all, delete-orphan"` 级联操作 Chunk、Claim、Relationship、Event。

---

### 3. Chunk

**表名：** `chunks`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `Integer` | PK, autoincrement | 分块 ID |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | 所属文档 |
| `chunk_index` | `Integer` | NOT NULL | 分块序号（从 0 开始） |
| `text` | `Text` | NOT NULL | 分块文本内容 |
| `title` | `String(500)` | | 分块标题（如有） |
| `section` | `String(200)` | | 所属章节 |
| `published_at` | `DateTime` | | 继承自文档的发布时间 |

---

### 4. Claim

**表名：** `claims`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `String(100)` | PK | 主张 ID（UUID 字符串） |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | 来源文档 |
| `text` | `Text` | NOT NULL | 主张文本 |
| `actor` | `String(100)` | NOT NULL | 发出主张的主体 |
| `topic` | `String(100)` | NOT NULL | 所属话题 |
| `stance` | `String(50)` | NOT NULL | 立场：`supportive`, `cautious`, `opposed`, `unclear` 等 |
| `confidence` | `Float` | NOT NULL | 提取置信度 [0, 1] |
| `published_at` | `DateTime` | | 主张对应原文的发布时间 |

---

### 5. Entity

**表名：** `entities`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `Integer` | PK, autoincrement | 实体 ID |
| `name` | `String(150)` | **UNIQUE**, NOT NULL | 实体名称（唯一，按名去重） |
| `type` | `String(100)` | | 实体类型：`person`, `organization`, `place`, `topic`, `concept` 等 |
| `description` | `Text` | | 实体描述 |

Entity 不直接通过外键关联 Document，而是通过 Relationship 的 `source_name` / `target_name` 字段间接引用。

---

### 6. Relationship

**表名：** `relationships`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `Integer` | PK, autoincrement | 关系 ID |
| `source_name` | `String(150)` | NOT NULL | 源实体名称（与 Entity.name 做软关联） |
| `target_name` | `String(150)` | NOT NULL | 目标实体名称（与 Entity.name 做软关联） |
| `relation_type` | `String(100)` | NOT NULL | 关系类型（如 `works_at`, `located_in`） |
| `description` | `Text` | | 关系描述 |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | 证据文档 |
| `confidence` | `Float` | 默认 `1.0` | 提取置信度 [0, 1] |
| `published_at` | `DateTime` | | 证据原文的发布时间 |

---

### 7. Event

**表名：** `events`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `Integer` | PK, autoincrement | 事件 ID |
| `title` | `String(250)` | NOT NULL | 事件标题 |
| `description` | `Text` | | 事件描述 |
| `event_date` | `DateTime` | NOT NULL | 事件发生时间 |
| `topic` | `String(100)` | | 所属话题 |
| `document_id` | `Integer` | FK → documents.id, ON DELETE CASCADE, NOT NULL | 证据文档 |
| `confidence` | `Float` | 默认 `1.0` | 提取置信度 [0, 1] |

---

## 模型关系图

```
SourceConfig (sources)
  │
  │  软关联 (source_name)
  ▼
Document (documents) ──┬──cascade──▶ Chunk (chunks)
  │                    ├──cascade──▶ Claim (claims)
  │                    ├──cascade──▶ Relationship (relationships)
  │                    └──cascade──▶ Event (events)
  │
  │  软关联 (source_name / target_name)     Entity (entities)
  │         ┌─────────────────────────────┘
  ▼         ▼
Relationship (relationships)
```

### 关键设计决策

| 决策 | 说明 |
|------|------|
| **Entity ↔ Relationship 基于名称关联** | Entity 与 Relationship 之间不设外键（FK），而是通过 `Entity.name` ↔ `Relationship.source_name` / `Relationship.target_name` 进行名称匹配。这样允许多个文档中提取的实体自然融合，避免跨文档的 ID 协调问题。 |
| **Document 级联删除** | Document 的 `cascade="all, delete-orphan"` 确保删除文档时自动清理其 Chunk、Claim、Relationship、Event 记录。外键均设置 `ON DELETE CASCADE`。 |
| **软关联 vs 外键** | SourceConfig→Document 通过 `source_name` 字符串软关联，而非外键。这样 Document 不依赖 SourceConfig 记录的存在，便于独立采集和回填。 |
| **Claim 使用 String PK** | Claim 的 `id` 为 UUID 字符串（`String(100)`），适合作为跨系统引用标识，避免整数自增 ID 在分布式场景下的冲突。 |

---

## Document 生命周期

Document 的 `status` 字段记录处理状态，由提取流水线（`softwiki/extraction/processor.py`）驱动：

```
┌─────────┐
│ pending │ ◄── 初始状态（background=True 入队）
└────┬────┘
     │
     ▼
┌───────────┐
│ extracting│ ◄── 后台线程或同步调用开始处理
└─────┬─────┘
     │
     ├── 成功 ──▶ ┌───────────┐
     │            │ completed │
     │            └───────────┘
     │
     └── 失败 ──▶ ┌────────┐
                  │ failed │
                  └────────┘
```

| 状态 | 含义 | 设置时机 |
|------|------|---------|
| `pending` | 文档已入库，等待提取 | `run_extraction_pipeline()` 中 `background=True` 时 |
| `extracting` | 提取进行中 | `_bg_extraction_worker()` 或同步 `run_extraction_pipeline()` 开始时 |
| `completed` | 提取全部完成 | 所有提取步骤（Claim、Graph、Timeline）成功执行后 |
| `failed` | 提取失败 | 任意步骤抛出异常，在 `except` 块中设置 |

> **注：** 直接导入（非 background 模式）时，文档创建后默认 status 为 `completed`，因为此时提取已在同步流程中完成。`pending`→`extracting` 转换仅出现在后台异步模式。

---

<!-- 
  本文件仅包含数据模型定义。
  查询/RAG 逻辑 → rag-engine.md
  提取流水线细节 → pipeline.md
-->
