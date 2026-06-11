# CLI 命令参考

> **范围**: SoftWiki CLI 所有命令、选项和示例的完整参考。
> **适用对象**: 使用终端的操作人员和高级用户。

---

## 全局选项

以下选项适用于所有命令，必须在命令之前指定：

| 选项 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--workspace` | `-w` | `str` | `WORKSPACE_DIR` 环境变量或 `workspace/default` | 指定工作区路径（绝对路径或名称） |
| `--mode` | | `choice` | `wiki-admin` | 执行模式：`wiki-admin`、`wiki-manage`、`wiki-study`、`wiki-work` |
| `--session-id` | | `str` | `None` | 会话 ID，用于输出路由（仅用户模式使用） |

**模式说明**:

| 模式 | 权限 | 用途 |
|------|------|------|
| `wiki-admin` | 读写 | 完全管理权限，可执行所有操作 |
| `wiki-manage` | 读写 | 管理工作区内容，无系统级操作 |
| `wiki-study` | 只读 | 仅查询和分析，禁止写入操作 |
| `wiki-work` | 只读 | 工作模式，仅查询和分析 |

> **注意**: `init`、`ingest`、`index` 在 `wiki-study` 和 `wiki-work` 模式下被禁用。`wiki build` 在 `wiki-study` 模式下被禁用。

启动时，CLI 会显示当前激活的工作区和模式：

```
[*] Active Workspace: /home/user/softwiki/workspace/my-project
[*] User Mode Active (WIKI-WORK). Session Output: output/ses_abc123/
```

---

## 命令参考

### `init` — 初始化工作区

初始化文件夹结构、配置文件和数据表。

**用法**:

```bash
softwiki [全局选项] init
```

**说明**: 创建以下目录结构：

```
workspace/<name>/
├── raw/html/
├── raw/pdf/
├── raw/markdown/
├── raw/api/
├── processed/documents/
├── processed/chunks/
├── processed/embeddings/
├── processed/extracted/
├── export/wiki/countries/
├── export/wiki/organizations/
├── export/wiki/topics/
├── export/wiki/events/
├── export/wiki/claims/
├── export/wiki/reports/
├── configs/sources.yaml
├── configs/model_profiles.yaml
└── scope.md
```

从模板目录复制默认配置文件（`sources.yaml`、`model_profiles.yaml`、`scope.md`），如果模板不存在则创建占位符。初始化数据库表并从 `sources.yaml` 中预填充源配置。

**示例**:

```bash
# 初始化默认工作区
softwiki init

# 初始化指定工作区
softwiki -w ~/research/my-project init
```

---

### `ingest` — 导入文档

导入文档，进行清理，提取元数据，运行提取流程（实体、关系、事件、声明），并保存到数据库。

**用法**:

```bash
softwiki [全局选项] ingest --url <URL> [--source-id <ID>]
softwiki [全局选项] ingest --file <PATH> [--source-id <ID>]
```

**选项**:

| 选项 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--url` | `str` | 见说明 | 从网页 URL 导入内容 |
| `--file` | `str` | 见说明 | 从本地 PDF 文件导入内容 |
| `--source-id` | `str` | 否 | 关联 `configs/sources.yaml` 中的预定义源 ID |

> `--url` 和 `--file` 必须至少指定一个，不能同时使用。

**流程**:

1. 获取内容（网页抓取或 PDF 提取）
2. 通过范围检查（`scope.md`）验证文档是否在范围内
3. 基于内容哈希和 URL 进行去重
4. 保存到文档数据库
5. 运行提取流程：实体、关系、事件、声明

**示例**:

```bash
# 从 URL 导入，不关联来源
softwiki ingest --url https://example.com/article

# 从 URL 导入，关联来源
softwiki ingest --url https://example.com/report --source-id world-bank

# 从本地 PDF 导入
softwiki ingest --file /path/to/document.pdf

# 从 PDF 导入，关联来源
softwiki ingest --file ./paper.pdf --source-id academic-journal
```

**输出**:

```text
Ingesting URL: https://example.com/article...
Created Document ID 42: 'Article Title'
Running extraction pipeline...
Extraction complete: 15 claims, 8 entities, 12 relationships, 3 events extracted.
```

---

### `index` — 重建搜索索引

为所有文档重建稠密向量索引（嵌入）和稀疏 BM25 关键词索引。

**用法**:

```bash
softwiki [全局选项] index
```

**说明**: 对工作区数据库中的每个文档，执行以下操作：

1. 删除现有块
2. 将清洗后的文本分块
3. 为所有块生成嵌入向量
4. 更新 FAISS 向量索引
5. 重建 BM25 关键词索引

**示例**:

```bash
# 重建所有索引
softwiki index

# 在另一个工作区重建索引
softwiki -w my-project index
```

**输出**:

```text
Building search indexes...
Indexing 156 chunks...
Generating embeddings...
Vector index successfully updated.
BM25 keyword index successfully updated.
Indexing complete!
```

---

### `ask` — 研究问答

使用混合 RAG 检索 + 图上下文 + LLM 综合的智能系统回答研究问题。

**用法**:

```bash
softwiki [全局选项] ask "<问题>"
```

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | `str` | 是 | 自然语言研究问题 |

**示例**:

```bash
# 基本研究问题
softwiki ask "What are the key drivers of de-dollarization?"

# 多语言查询
softwiki ask "各国央行黄金储备变化趋势如何？"

# 在特定工作区中提问
softwiki -w geo-economics ask "How has BRICS expansion affected USD reserve share?"
```

**输出**: 包含引用的综合回答，源自检索到的块和图上下文。

---

### `wiki` — Wiki 页面管理

#### `wiki build` — 构建 Wiki 页面

为指定主题 ID 编译并生成 Markdown wiki 页面。

**用法**:

```bash
softwiki [全局选项] wiki build --topic <TOPIC_ID>
```

**选项**:

| 选项 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--topic` | `str` | 是 | 要构建页面的主题 ID |

> 在 `wiki-study` 模式下禁用。

**示例**:

```bash
# 构建国家主题的 wiki 页面
softwiki wiki build --topic de-dollarization

# 构建组织主题的 wiki 页面
softwiki wiki build --topic world-bank
```

**输出**:

```text
Generating wiki page for topic: 'de-dollarization'...
Wiki page successfully written to: /path/to/workspace/export/wiki/topics/de-dollarization.md
```

---

### `shell` — 启动交互式 TUI

启动交互式研究和管理的终端用户界面（TUI）。

**用法**:

```bash
softwiki [全局选项] shell [选项]
```

**选项**:

| 选项 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--workspace` | `-w` | `str` | `WORKSPACE_DIR` 或 `workspace/default` | 工作区名称或路径 |
| `--model` | `-m` | `str` | `ANALYSIS_MODEL` 或 `gemini-2.5-flash` | 用于分析的模型 |
| `--session` | `-s` | `str` | `None` | 自定义会话名称后缀。终端会话 ID = `{workspace}-{mode}-{session}` |

> **注意**: `--model` 和 `--session` 是 TUI 帮助命令的全局标志。通过 TUI 发出的命令应通过 `open-code` 工作流使用，该工作流使用在 `shell` 启动时注入的上下文调用工具。

**示例**:

```bash
# 启动默认工作区的 TUI
softwiki shell

# 启动特定工作区和模型的 TUI
softwiki -w geo-economics shell -m gemini-2.5-pro

# 启动具有自定义会话名称的 TUI
softwiki shell --workspace my-project --session round-2
```

---

### `api` — 启动 REST API 服务器

启动 REST API 服务器。

**用法**:

```bash
softwiki [全局选项] api [选项]
```

**选项**:

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--port` | `int` | `8000` | API 服务器的端口 |
| `--host` | `str` | `127.0.0.1` | API 服务器绑定的主机 |

**示例**:

```bash
# 在默认地址启动 API 服务器
softwiki api

# 在自定义端口启动 API 服务器
softwiki api --port 9000

# 绑定到所有接口
softwiki api --host 0.0.0.0 --port 8080
```

---

### `graph` — 图谱管理

#### `graph list` — 列出实体和关系

列出工作区中所有已提取的实体和关系。

**用法**:

```bash
softwiki [全局选项] graph list
```

**输出**:

```text
=== Entities (24) ===
- United States [country]: Federal republic in North America
- Federal Reserve [organization]: Central bank of the United States
- USD [currency]: United States Dollar
- BRICS [organization]: Intergovernmental organization

=== Relationships (47) ===
- United States --(imposes_sanctions_on)--> Russia (Conf: 0.92)
  Note: Sanctions imposed after 2022 invasion
- China --(holds_reserves_in)--> USD (Conf: 0.85)
```

---

### `timeline` — 时间线管理

#### `timeline list` — 列出时间线事件

按时间顺序列出工作区中所有已提取的事件。

**用法**:

```bash
softwiki [全局选项] timeline list
```

**输出**:

```text
=== Chronological Events (12) ===
- [2022-02-24] Russia-Ukraine Conflict Begins (Topic: geopolitics)
  Description: Full-scale invasion of Ukraine by Russia
- [2023-08-22] BRICS Summit 2023 (Topic: international-relations)
  Description: BRICS announces expansion to include new members
- [2024-10-22] BRICS Summit 2024 (Topic: international-relations)
  Description: Further discussion on de-dollarization and trade settlement
```

---

## 退出码

| 退出码 | 含义 |
|--------|------|
| `0` | 成功 |
| `1` | 一般错误（无效参数、操作失败、文档超出范围等） |

---

## 使用模式

### 管理工作区

```bash
# 初始化并设置
softwiki -w my-research init

# 导入文档
softwiki -w my-research ingest --url https://example.com/article --source-id source-1
softwiki -w my-research ingest --file ./papers/report.pdf

# 重建索引
softwiki -w my-research index
```

### 研究查询

```bash
# 在只读模式下查询
softwiki -w my-research --mode wiki-work ask "What are the latest developments?"

# 启动 TUI 进行交互式研究
softwiki -w my-research --mode wiki-work shell
```

### Wiki 发布

```bash
# 生成并查看主题页面
softwiki wiki build --topic my-topic
```
