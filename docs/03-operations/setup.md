# 安装与设置

> **范围**：系统要求、Python 环境、工作空间初始化、配置模板、多工作空间管理、MCP Server 注册。
>
> **前置阅读**：[架构概览](../01-architecture/overview.md) | [接口文档](../01-architecture/interfaces.md)

---

## 系统要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | 运行 Core、CLI、MCP Server |
| Node.js | 18+ | 仅 WebUI 需要 |
| opencode | — | 仅 Shell TUI 需要 |

**已知兼容的 LLM Provider**：

- OpenAI（GPT-4o / GPT-4o-mini / text-embedding-3-small）
- DeepSeek（通过 OpenAI 兼容接口）
- Gemini（通过 OpenAI 兼容接口）
- Groq（通过 OpenAI 兼容接口）

Embedding Provider 支持 `openai`（API）或 `local`（基于 sentence-transformers）。

---

## 安装

### 1. 克隆项目

```bash
git clone <repo-url> softwiki
cd softwiki
```

### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装包

```bash
# 基础安装（RAG + Core + MCP + API）
pip install -e .

# 完整安装（含开发工具和 LightRAG GraphRAG）
pip install -e ".[dev,graph]"
```

可选依赖组：

| 组 | 包含 | 用途 |
|----|------|------|
| `[dev]` | pytest | 运行测试套件 |
| `[graph]` | lightrag-hku | 知识图谱多跳推理查询 |

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
OPENAI_API_KEY=sk-...           # LLM API Key
OPENAI_API_BASE=https://...     # API 端点（可选，默认 OpenAI）
EXTRACTION_MODEL=gpt-4o-mini    # 提取用模型
ANALYSIS_MODEL=gpt-4o           # 分析与合成用模型
EMBEDDING_PROVIDER=openai       # 嵌入 Provider
EMBEDDING_MODEL=text-embedding-3-small
```

环境变量自动从 `.env` 加载（`softwiki/config.py:load_env()`），也可通过 shell export 覆盖。

### 5. 验证安装

```bash
./sw --help
```

应显示 SoftWiki CLI 命令列表。

---

## 初始化工作空间

工作空间（Workspace）是 SoftWiki 中**独立的知识库单元**，包含文档、索引、配置和数据库，以文件系统目录组织。

### 默认工作空间

```bash
./sw init
```

在 `workspace/default/` 创建以下结构：

```
workspace/default/
├── config/               # 工作空间配置
│   ├── scope.md          # 知识库范围定义
│   ├── topics.yaml       # 研究主题定义
│   ├── sources.yaml      # 数据源信任级别
│   ├── model_profiles.yaml
│   ├── workflows.yaml
│   └── agents.md         # Agent 提示词覆盖（可选）
├── raw/                  # 原始文件
│   ├── html/
│   ├── pdf/
│   ├── markdown/
│   └── api/
├── .softwiki/            # 数据库与索引
│   ├── processed.db      # SQLite 数据库
│   ├── index/            # 向量 & BM25 索引
│   └── lightrag/         # LightRAG 图数据
├── exports/              # 导出产物
│   └── wiki/             # Wiki 页面
│       ├── topics/
│       ├── organizations/
│       ├── countries/
│       ├── events/
│       ├── claims/
│       └── reports/
└── processed/            # 处理中间产物（嵌入向量等）
    ├── documents/
    ├── chunks/
    ├── embeddings/
    └── extracted/
```

`init` 命令自动完成：

1. 创建上述文件夹结构
2. 从 `softwiki/templates/` 复制默认配置文件到 `config/`
3. 创建 SQLite 数据库（`.softwiki/processed.db`）
4. 从 `config/sources.yaml` 预置数据源记录

### 自定义路径

```bash
./sw -w workspace/my-kb init
```

支持任意路径：

```bash
./sw -w /data/research/knowledge-base init
```

---

## 多工作空间

每个工作空间完全隔离，拥有独立的数据库、索引、配置和数据文件。

### 切换方式

**方式一：`-w` 参数**

```bash
# 使用不同工作空间
./sw -w workspace/kb-alpha ingest --url "https://..."
./sw -w workspace/kb-beta ask "核心发现？"
```

**方式二：环境变量**

```bash
export WORKSPACE_DIR=/data/research/kb-alpha
./sw init
./sw ingest --url "https://..."
```

**方式三：路径格式**

`-w` 接受相对路径（相对于项目根目录）或绝对路径：

```bash
./sw -w workspace/my-kb shell       # 相对路径
./sw -w /home/user/my-kb shell      # 绝对路径
```

### 使用场景

| 场景 | 实践 |
|------|------|
| 独立研究课题 | 每个课题独立工作空间 |
| 团队共享 | 每个研究者独立工作空间，通过 `workspace/` 目录共享 |
| 分阶段研究 | 第一阶段、第二阶段可分离至不同工作空间 |
| 生产/测试隔离 | 生产库和测试库使用不同工作空间 |

---

## 配置模板

工作空间初始化后，`config/` 目录包含以下配置文件：

### scope.md — 知识库范围

定义知识库的话题边界，供 `scope_guard` 在摄入文档时自动过滤。

```markdown
# Knowledge Base Scope

## In Scope
- De-dollarization, central bank reserves, gold, international trade currencies.

## Out of Scope
- Unrelated financial news, stock market updates, recipes, entertainment, sports.
```

### topics.yaml — 研究主题定义

```yaml
topics:
  topic-alpha:
    aliases:
      - topic a
      - alpha project
      - 第一主题
    related:
      - topic-beta
      - topic-gamma

  topic-beta:
    aliases:
      - topic b
      - beta system
      - 第二主题
    related:
      - topic-alpha
```

每个主题包含别名字段（用于匹配）和相关主题列表（用于 Wiki 页面交叉引用）。

### sources.yaml — 数据源信任级别

```yaml
sources:
  - id: sample_source_1
    name: Sample News Outlet
    type: news                       # official / news / think_tank / academic
    url: https://www.example-news.com/
    trust_level: high                # high / medium / low
    source_country: us
    language: en
```

`init` 命令会将 `sources.yaml` 中的所有源预置到数据库，后续摄入可通过 `--source-id` 参数关联。

### model_profiles.yaml — LLM 参数覆盖

```yaml
profiles:
  cheap_extraction:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.0

  high_quality_analysis:
    provider: openai
    model: gpt-4o
    temperature: 0.2

  local_embedding:
    provider: local
    model: bge-m3
```

可通过环境变量 `EXTRACTION_MODEL`、`ANALYSIS_MODEL` 等覆盖默认模型选择。

### workflows.yaml — 工作流覆盖

定义 Agent shell 中使用的自路由工作流。默认提供 `research`、`wiki-compile`、`contribute`、`submit`、`simple-q&a` 五个工作流。工作空间级配置会与默认模板进行**深度合并**。

### agents.md — Agent 提示词覆盖

可选的 Agent 行为覆盖文件。放置在 `config/agents.md` 后，Shell TUI 启动时会自动加载并追加至默认 Agent Soul 之后，用于自定义 Agent 的行为模式、工具边界和响应格式。

---

## 注册 MCP Server

SoftWiki 通过 Model Context Protocol（MCP）将知识库能力暴露给外部 AI 工具。MCP Server 以独立进程运行，通过 stdio JSON-RPC 通信。

### 通用配置

将以下 JSON 加入 AI 工具的 MCP 配置：

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

### 各平台配置位置

**Claude Desktop**：编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）。

**Cursor**：在 Cursor 设置中配置 MCP Servers 列表。

**opencode**：编辑 `opencode.json` 或 `.opencode/mcp.json`。

**自定义 MCP 客户端**：任何支持 MCP 协议的客户端均可通过 stdio 方式连接。

### 只读模式

若要限制外部工具仅能查询，设置环境变量：

```json
"env": {
  "SOFTWIKI_MODE": "wiki-study",
  "WORKSPACE_DIR": "...",
  "PYTHONPATH": "..."
}
```

四种运行模式见 [架构概览-运行模式](../01-architecture/overview.md#运行模式)。

---

## 验证安装

### CLI 工作流

```bash
# 1. 初始化默认工作空间
./sw init

# 2. 摄入一篇文档
./sw ingest --url "https://example.com/article"

# 3. 重建索引
./sw index

# 4. 提问
./sw ask "文章的核心观点是什么？"

# 5. 编译 Wiki 页面
./sw wiki build --topic topic-alpha
```

### MCP Server 心跳

MCP Server 启动后无日志输出（stdio 协议），可通过外部 MCP 客户端调用 `softwiki_status` 工具验证连接。

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `./sw: No such file or directory` | 虚拟环境未创建 | `python3 -m venv venv && source venv/bin/activate && pip install -e .` |
| `ModuleNotFoundError: softwiki` | PYTHONPATH 未设置 | `sw` 脚本已自动设置；手动运行时需 `export PYTHONPATH=.` |
| 摄入文档被拒绝（out of scope） | `config/scope.md` 范围过窄 | 编辑 `scope.md` 扩大范围 |
| MCP 连接失败 | `WORKSPACE_DIR` 路径错误 | 确认 `PYTHONPATH` 和 `WORKSPACE_DIR` 均使用绝对路径 |
