# Softwiki: 基于多层知识合成的研究智能系统技术白皮书
## Whitepaper: Research Intelligence System & Multi-Layer Knowledge Synthesis

> [!NOTE]
> **文档状态**：本文为技术设计白皮书，描述 Softwiki 的整体技术架构与设计哲学。
> 当前实现状态请参见 [project-status.md](project-status.md)。

## 元数据记录 (Metadata)

* **白皮书名称**: Softwiki 知识库与研究智能系统技术白皮书
* **版本**: v1.1.0
* **更新日期**: 2026-06-09
* **状态**: 活跃/已实施 (Active / Implemented)
* **主项目路径**: `.` (仓库根目录)
* **核心技术栈**: Python 3.10+ + SQLite/SQLAlchemy + FastMCP + OpenAI-compat API
* **目标受众**: 学术研究人员、领域分析专家、系统研发工程师

---

## 摘要 (Abstract)

在当今科学研究与宏观情报分析中，研究人员面临着前所未有的**信息过载（Information Overload）**与**证据校验危机（Verification Crisis）**。传统的大语言模型（LLM）因缺乏可追溯的实体引用而容易产生“幻觉”；而普通的检索增强生成（RAG）方案由于其“无状态（Stateless）”和“碎片化”的特点，无法帮助研究者把握复杂的文献脉络、时间线演进以及多方立场博弈。

为了解决上述痛点，本项目设计并实现了 **Softwiki**：一个面向学术界及专业分析领域的**通用、领域无关的研究智能与多层知识合成系统**。Softwiki 坚守“**原始文献为唯一真实证据源 (Source of Truth)**”的严谨科学原则，通过提取引擎自动编译出五个高度解耦、可灵活插拔的派生知识视图。本白皮书旨在阐述 Softwiki 的技术架构、设计哲学及其在支撑高可信度学术研究与决策情报分析中的应用。

---

## 1. 核心设计哲学与架构概述

学术研究与情报分析的严谨性要求系统具备极高的“证据可追溯性”与“多方认知视角”。Softwiki 的核心设计遵循以下原则：

1. **以源文献为唯一证据锚点 (Source-Grounded Architecture)**：所有的关系图谱、立场声明和事件线，都必须由系统算法精确溯源至最初导入的 PDF 或网页段落。彻底杜绝黑盒大模型的无端臆测与学术幻觉。
2. **多维认知视图的解耦与插拔 (Decoupled Multi-View Synthesis)**：RAG 语义片段、GraphRAG 关系网络、Claims 观点立场、Timeline 时间线，以及 LLM-Wiki 本地知识累积，相互独立而又紧密协同，研究者可根据研究领域的特殊性灵活增减配置。
3. **从无状态 RAG 到有状态的本地知识沉淀 (Stateful Knowledge Compounding)**：借鉴 Andrej Karpathy 提出的 **`llm-wiki.md`** 架构模式，系统能够基于导入文献，在本地自动归纳并演进出一套人类可读的 Markdown 知识库页面，实现知识随着研究深入而持续积累增重。

系统整体拓扑结构如下：

```text
                           ┌───────────────────────────┐
                           │        Raw Sources        │
                           │   (web_loader/pdf_loader) │
                           └─────────────┬─────────────┘
                                         ↓
                           ┌───────────────────────────┐
                           │       Source Store        │
                           │    (DocumentRepository)   │
                           └─────────────┬─────────────┘
                                         ↓
   ┌───────────────────┬─────────────────┼─────────────────┬───────────────────┐
   ↓                   ↓                 ↓                 ↓                   ↓
┌──────────────┐┌──────────────┐ ┌──────────────┐┌──────────────┐┌──────────────┐
│  RAG Index   ││   Claim DB   │ │   LLM Wiki   ││  Knowledge   ││   Timeline   │
│(LocalVector  ││              │ │  WikiPage-   ││   Graph DB   ││  Timeline-   │
│/Bm25Store)   ││ClaimExtractor│ │  Generator   ││GraphExtractor││  Extractor   │
└──────┬───────┘└──────┬───────┘ └──────┬───────┘└──────┬───────┘└──────┬───────┘
       │               │                │               │               │
       └───────────────┴────────────────┼───────────────┴───────────────┘
                                        ↓
                           ┌───────────────────────────┐
                           │   Answer Engine Router    │
                           │      (AnswerEngine)       │
                           └─────────────┬─────────────┘
                                         ↓
                           ┌───────────────────────────┐
                           │      Wiki / Reports       │
                           │   (WikiPanel / Exports)   │
                           └───────────────────────────┘
```

系统包含以下关键自定义工具组件与类：
* **`DocumentRepository`**：管理原始文献和片段的底层数据库读取与存储。
* **`LocalVectorStore`** / **`Bm25Store`** / **`HybridSearcher`**：实现局部语义检索、BM25 关键字检索及混合检索排序。
* **`ClaimExtractor`**：提取原始文献中各个主体的立场（Stance）、置信度与主张（Claim）。
* **`GraphExtractor`**：提取实体与实体关系并管理知识图谱。
* **`TimelineExtractor`**：抽取具有发生日期的历史事件并生成时序事件线。
* **`WikiPageGenerator`**：为用户关注的研究课题生成并增量更新 Markdown Wiki 报告。该组件实现了由 Andrej Karpathy 提出的 **`llm-wiki.md`** 架构思想，通过将分散的原始文献碎片融合成高内聚、长久持存且互相关联的本地 Markdown 知识库页面，使得系统能基于演进的知识视图（而非单纯无状态片段）进行高阶推理。
* **`AnswerEngine`**：底层问答路由引擎，综合调度并聚合这五种派生知识视图的信息，合成多维上下文。
* **`WikiPanel`** / **`ChatPanel`** / **`IngestPanel`** / **`DocumentsPanel`** / **`ClaimsPanel`**：前端用户交互的核心 React 页面面板组件。

---

## 2. 数据层设计 (SQL Schema)

数据库位于每个 Workspace 目录下的 `softwiki.db` (SQLite 格式)。数据表模型在 [models.py](../softwiki/source_store/models.py) 中定义，包含以下核心实体：

### 2.1 文档与片段模型
* **`Document`**: 存储原始与清洗后的网页/PDF文本及其采集元数据（国家、可信度等级、发布日期）。
* **`Chunk`**: 用于 RAG 检索的文档分片，关联 `Document` 并执行级联删除。

### 2.2 派生知识模型
* **`Claim`**: 结构化主张。记录 Actor（表态主体）、Stance（立场：supportive/cautious/opposed/unclear）、Confidence（置信度）和具体的 Claim 描述文本。
* **`Entity`**: 知识图谱实体。记录实体 Name（唯一）、Type（如 country, organization, person, concept, location, project）以及 Description。
* **`Relationship`**: 图谱关系边。连接 `source_name` 与 `target_name`，定义 `relation_type` 并关联来源 `Document`。
* **`Event`**: 对应时间线。记录具有具体发生日期 `event_date` 的事件、对应 `topic` 以及描述信息。

---

## 3. 模块化与增量提取管道 (Extraction Pipeline)

Softwiki 采用**增量编译与提取 (Incremental Extraction)** 机制，所有知识视图的抓取与检索都是模块化的。

### 3.1 模块开关配置
通过环境变量 **`ENABLED_MODULES`** 配置当前启用的视图（默认为全部启用：`rag,graph,claimdb,timeline,llmwiki`）。可通过 [config.py](../softwiki/config.py) 中的 **`is_module_enabled(name)`** 动态查询状态。

### 3.2 统一的管道入口 [processor.py](../softwiki/extraction/processor.py)
在导入新文档时，**`run_extraction_pipeline`** 会根据开关动态调用不同的提取器，避免在 CLI, REST API 和 MCP 之间出现重复代码：

```python
def run_extraction_pipeline(db: Session, doc_id: int, cleaned_text: str, published_at: datetime) -> dict:
    # 1. 提取 Claim（如果启用 claimdb）
    # 2. 提取 Entity & Relationship（如果启用 graph）
    # 3. 提取 Event（如果启用 timeline）
```

### 3.3 提取器提取规则
系统针对三种增量视图配备了专门的提取器类：**`ClaimExtractor`**、**`GraphExtractor`** 和 **`TimelineExtractor`**。
* **大模型驱动（在线模式）**：当配置有效的 **`OPENAI_API_KEY`** 时，采用 [graph_extractor.py](../softwiki/extraction/graph_extractor.py) 中的 **`GraphExtractor`** 和 [timeline_extractor.py](../softwiki/extraction/timeline_extractor.py) 中的 **`TimelineExtractor`** 向 LLM 发送带有 JSON Schema 约束 of Prompt 进行实体关系与时序事件的精准提取。
* **规则启发式驱动（本地 fallback 模式）**：如果 API Key 缺失，提取器将自动降级为本地启发式提取，动态扫描预定义的国家和组织列表提取提及实体，并利用年份正则提取含有日期特征的句子作为时序事件。

---

## 4. 问答引擎与上下文路由 (Answer Engine)

问答引擎 [answer_engine.py](../softwiki/intelligence/answer_engine.py) 改变了传统 RAG 仅检索文本片段的做法。其检索流程如下：

1. **RAG 检索**：调用 **`HybridSearcher`** 统一路由检索，使用 **`LocalVectorStore`** 从局部向量库查找相似度最高的文本片段，并配合 **`Bm25Store`** 执行关键字 BM25 索引匹配，最后混合重排抓取 Top K 相关片段（RAG 视图启用时）。
2. **ClaimDB 检索**：提取问题中的主要实体关键词，查询通过 **`ClaimExtractor`** 抽取的 Actor 立场主张记录（ClaimDB 视图启用时）。
3. **Graph 检索**：获取问题中相关实体，查询通过 **`GraphExtractor`** 提取的 Entity 与 Relationship，拼接出结构化的上下文关系网（Graph 视图启用时）。
4. **Timeline 检索**：抓取并整理通过 **`TimelineExtractor`** 抽取的 Event 列表，按发生日期正序编排历史时序线（Timeline 视图启用时）。
5. **Wiki 缓存检索**：如果用户曾针对该主题通过 **`WikiPageGenerator`** 编译生成过 Wiki 报告，则读取对应的局部 Markdown 知识库片段（LLMWiki 视图启用时）。

最终，引擎将上述各维度拼接为多维上下文（Multidimensional Context）送入 LLM 合成出高度翔实、有理有据并附带精确引用标记的分析报告。

---

## 5. 用户端接口实现 (User Interfaces)

### 5.1 CLI / TUI 交互式终端 (Fallback Shell)
在 [shell.py](../softwiki/cli/shell.py) 中，系统启动时会检测是否安装了外部 **`opencode`** 可执行程序：
* **已安装**：配置工作空间 MCP Server 环境并直接 exec 进入 OpenCode 终端界面。
* **未安装**：自动启动 Softwiki 自研的 Python REPL Fallback 终端。交互命令行提供以下命令：
  * `/status`：展示当前工作空间位置、数据库状态和各激活模块开关。
  * `/ask <question>`：调用底层 **`AnswerEngine`** 发起多维知识检索问答。
  * `/ingest <url_or_file>`：支持直接网络爬取或上传本地 PDF，并触发一键增量提取。
  * `/index`：清空并重新构建向量与关键字搜索索引。
  * `/wiki <topic>`：调用 **`WikiPageGenerator`** 编译合成指定话题的 Markdown Wiki 报告。

### 5.2 CLI 独立管理指令 [main.py](../softwiki/cli/main.py)
新增了以下指令用于运维排查：
* `sw graph list`：将图谱中所有的 Entities 与 Relationships 结构化格式化输出至终端。
* `sw timeline list`：按事件发生时间（正序）打印时间线。

### 5.3 FastAPI REST 接口 [server.py](../softwiki/api/server.py)
供前端 Next.js 服务调用的 API 路由：
* `GET /api/status`：获取库文档数、分片数、主张数、图谱与事件数、当前激活模块列表。
* `POST /api/ask`：多维检索答复接口。
* `POST /api/ingest/url` / `POST /api/ingest/file`：抓取与上传接口，集成了增量提取。
* `GET /api/documents` / `DELETE /api/documents/{id}`：文献列表及级联删除接口。
* `GET /api/claims`：获取所有提取出的立场声明及置信度。
* `GET /api/timeline`：正序拉取全量历史事件线。
* `GET /api/graph`：输出全量 Entities 和 Relationships 以渲染关联网络。
* `GET /api/wiki/topics` / `POST /api/wiki/build`：获取受监控议题和执行 Wiki 重新编译。

---

## 6. Next.js 页面与交互面板

前端界面以极客风深色半透明玻璃化（Glassmorphism）为基调，样式表使用 Vanilla CSS 定义于 [globals.css](../web/app/globals.css)。主要面板位于 `web/components/`：

1. **研究对话框 (**`ChatPanel.tsx`**)**：
   * 自动路由问答，右侧可滑出源文献细节侧边栏 (**`SourceDrawer`**)。
2. **源文献导入板 (**`IngestPanel.tsx`**)**：
   * 支持通过 Drag & Drop 上传本地 PDF，并实时在终端显示后台提取日志。支持一键重建索引。
3. **数据中心板 (**`DocumentsPanel.tsx`**)**：
   * 以列表形式查看所有 ingested 的原始数据，支持显示可信度徽章并调用 **`DocumentRepository`** 执行一键文献彻底删除（级联清空关联的 chunks/claims/graph/events）。
4. **主张展示板 (**`ClaimsPanel.tsx`**)**：
   * 将由 **`ClaimExtractor`** 提取到的 Actor 的 Stance 信息以看板表格形式展示，支持对 Actor（表态主体）和 Stance（支持/谨慎/反对）执行前端即时条件检索。
5. **Wiki 预览板 (**`WikiPanel.tsx`**)**：
   * 选择受监视主题，调用 **`WikiPageGenerator`** 一键在工作空间 exports 目录下重新编译出 Markdown 知识页，并在前端通过 `react-markdown` 预览编译结果。

---

## 7. 部署与验证命令

### 7.1 后台环境部署
1. 激活虚拟环境并安装依赖：
   ```bash
   source venv/bin/activate
   pip install -e .
   ```
2. 初始化工作空间数据表（包含新建的图谱与时间线表格）：
   ```bash
   ./venv/bin/python -m softwiki.cli.main init
   ```
3. 启动 REST API 服务：
   ```bash
   ./venv/bin/python -m softwiki.cli.main api --port 8000
   ```

### 7.2 前端环境部署
1. 编译并打包前端静态页面：
   ```bash
   cd web
   npm run build
   ```
2. 启动前端开发调试服务器：
   ```bash
   npm run dev
   ```

---

## 8. 未来规划：容器化 (Dockerization) 考量

虽然当前阶段不执行容器化构建，但系统架构在设计上已为未来容器化做好了准备：

### 8.1 后端容器化 (Python FastAPI)
* **基础镜像**：可选用官方轻量级 `python:3.10-slim` 作为基础镜像。
* **数据持久化**：SQLite 数据库及工作空间配置默认保存在 `data/` 目录中。在 Docker 中部署时，需要通过 `-v` (Volume) 将主机的 `data/` 目录挂载到容器内的 `/app/data` 下，以确保 Workspace 数据持久化不丢失。
* **依赖安装**：通过 `Dockerfile` 复制 `pyproject.toml` 并运行 `pip install .`。

### 8.2 前端容器化 (Next.js)
* **基础镜像**：选用官方 `node:18-alpine`。
* **多阶段构建 (Multi-stage Build)**：
  1. 阶段一（依赖安装与编译）：拷贝前端代码并执行 `npm run build`。
  2. 阶段二（轻量运行）：仅拷贝编译产物 `.next/standalone` 和静态资源 `public`，以大幅压缩生成的 Docker 镜像体积。
* **环境变量**：在运行时通过 `NEXT_PUBLIC_API_URL` 动态将请求指向后台 FastAPI 容器。

### 8.3 容器编排 (Docker Compose)
未来可通过 `docker-compose.yml` 编排前后端：
* **`softwiki-backend`**：暴露 `8000` 端口，挂载持久化工作空间卷。
* **`softwiki-frontend`**：暴露 `3000` 端口，通过容器内网络联通后台服务，提供一键式、零配置的沙箱运行体验。

