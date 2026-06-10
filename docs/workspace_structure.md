# File System & Workspace Structure Guide

**更新日期**：2026-06-09

---

## 1. Engine Root Directory Layout

```text
softwiki/
├── README.md
├── pyproject.toml
├── setup.py
├── .env.example
├── Makefile
├── sw                      # CLI 快捷脚本
│
├── softwiki/               # 主引擎源码包
│   ├── config.py           # 路径函数 & 环境变量解析
│   ├── templates/          # 默认配置模板（随包分发）
│   │   ├── agent_soul.md
│   │   ├── workflows.yaml
│   │   ├── sources.yaml
│   │   └── model_profiles.yaml
│   ├── source_store/       # SQLite ORM 模型
│   ├── ingestion/          # 文档摄入（web / pdf / dedup / file_store）
│   ├── rag/                # 检索索引（chunker / embedder / vector / bm25 / hybrid）
│   ├── extraction/         # LLM 知识抽取（claim / graph / timeline / processor）
│   ├── intelligence/       # 问答引擎（answer_engine / llm_client / scope_guard）
│   ├── wiki/               # Wiki 页面生成
│   ├── mcp/                # MCP server（FastMCP stdio）
│   ├── api/                # REST API（FastAPI，供 WebUI 使用）
│   └── cli/                # CLI & Shell TUI
│
├── workspace/              # 工作空间根目录
│   ├── default/            # 默认工作空间
│   └── eva-kb/             # EVA 研究知识库（示例）
│
├── web/                    # WebUI（Next.js，独立子项目）
├── scripts/                # 辅助脚本（seed_eva.py 等）
├── tests/                  # 测试套件
└── docs/                   # 文档目录
```

---

## 2. Workspace Directory Layout

每个工作空间是完全自包含的目录，切换只需改 `WORKSPACE_DIR` 环境变量。

```text
workspace/my-domain/
│
├── raw/                        # 原始来源文件（第一手材料）
│   ├── html/                   # 抓取的网页原始 HTML（<hash>.html）
│   └── pdf/                    # 上传的 PDF 原件（<doc_id>_<filename>.pdf）
│
├── .softwiki/                  # SoftWiki 内部数据（机器生成，隐藏目录）
│   ├── processed.db            # SQLite 数据库（唯一真实数据源）
│   │                           # 表：documents / chunks / claims /
│   │                           #      entities / relationships / events
│   ├── md/                     # 清洗后的文档文本（<doc_id>_<slug>.md）
│   ├── chunks/                 # 分块 JSON（<doc_id>.json）
│   ├── extractions/            # LLM 抽取结果（<doc_id>.json）
│   │                           # 包含：claims / entities / relationships / events
│   └── index/                  # 检索索引缓存
│       ├── vector_index.npz    # NumPy dense 向量索引
│       └── bm25_index.pkl      # BM25 关键词索引
│
├── config/                     # 工作空间专属配置
│   ├── scope.md                # 知识库范围定义（In Scope / Out of Scope）
│   ├── sources.yaml            # 数据源（信任级别、来源类型）
│   ├── topics.yaml             # 研究主题定义（用于 Claim 抽取和 Wiki 生成）
│   ├── model_profiles.yaml     # LLM 参数覆盖（可选）
│   ├── workflows.yaml          # 工作流覆盖（可选）
│   └── agents.md               # Agent 提示词覆盖（可选）
│
└── exports/                    # 对外输出
    └── wiki/
        └── topics/             # WikiPageGenerator 生成的 Markdown 页面
            └── <topic-id>.md
```

### 目录职责说明

| 目录 | 读写者 | 说明 |
|------|--------|------|
| `raw/` | ingest pipeline 写，人工可查 | 原始来源，可追溯，不可再生 |
| `.softwiki/` | SoftWiki 全程管理 | 机器产出，可从 raw + config 重建 |
| `.softwiki/processed.db` | Core 唯一读写 | 真实数据源，其他文件均为派生 |
| `.softwiki/md/` | ingest 写，人工可读 | 清洗后全文，便于调试 |
| `.softwiki/chunks/` | index 写 | 分块详情，便于调试 |
| `.softwiki/extractions/` | extraction 写 | 每文档的抽取快照 |
| `.softwiki/index/` | index 写，search 读 | 向量 + BM25 检索索引 |
| `config/` | 人工维护 | 知识库配置，影响抽取和问答行为 |
| `exports/` | wiki_build 写，人工 / WebUI 读 | 最终输出，可直接发布 |

---

## 3. Pipeline 数据流

```text
URL / PDF
    ↓ ingestion（web_loader / pdf_loader）
raw/html/ 或 raw/pdf/             ← Stage 1: 原始文件落盘
    ↓ 清洗 normalize_text
.softwiki/md/<doc_id>.md          ← Stage 2: 清洗文本落盘
.softwiki/processed.db documents  ← 入库
    ↓ chunker（增量，ingest 时立即执行）
.softwiki/chunks/<doc_id>.json    ← Stage 3: 分块落盘
.softwiki/index/                  ← 增量 append（vector + BM25）
    ↓ LLM extraction（后台线程）
.softwiki/extractions/<doc_id>.json ← Stage 4: 抽取结果落盘
.softwiki/processed.db claims/entities/relationships/events ← 入库
    ↓ wiki_build（按需触发）
exports/wiki/topics/<topic>.md    ← Stage 5: Wiki 页面输出
```

---

## 4. 关键配置文件

### config/scope.md
定义知识库范围，`ingest` 时由 `scope_guard.py` 检查。未定义时默认全部接受。

### config/topics.yaml
```yaml
topics:
  topic-id:
    name: "Topic Display Name"
    description: "..."
    synonyms: ["alias1", "alias2"]
```
用于 `ClaimExtractor` 的主题分类和 `WikiPageGenerator` 的页面生成。

### config/sources.yaml
```yaml
sources:
  - id: source-id
    name: "Source Name"
    type: encyclopedia      # official / news / analysis / primary_source
    trust_level: medium     # high / medium / low
    source_country: jp
    language: ja
```

---

## 5. Docker 挂载示例

```bash
docker run \
  -v /path/to/host/my-kb:/workspace \
  -e WORKSPACE_DIR=/workspace \
  softwiki-image \
  softwiki ask "问题"
```

代码和工作空间完全分离，容器只读写 `/workspace`。
