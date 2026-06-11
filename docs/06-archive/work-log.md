# Softwiki 开发与架构设计决策工作日志 (Softwiki Development & Architecture Work Log)

本日志记录了 Softwiki 项目在开发迭代过程中所做的核心架构决策、技术权衡及业务流程设计，方便团队后续追溯和参考。

---

## 📅 2026-06-07

### 决策一：软路由模式命名规范化 (`wiki-xxxx` 命名空间)
*   **背景**：为了将 Softwiki 的工作模式与宿主终端 OpenCode 原生的模式（如 `sisyphus`, `plan`, `build` 等）隔离开来，并且让用户能够非常明确地识别当前处于 Softwiki 特定的研究子沙箱环境中。
*   **具体修改**：
    *   将原本的 `study`、`work`、`manage`、`admin` 模式，全部加上统一的前缀命名空间，变更为：`wiki-study`、`wiki-work`、`wiki-manage` 和 `wiki-admin`。
    *   在 `opencode.json` 生成器中，将内置的 OpenCode 智能体（如 `sisyphus` 等）全部禁用 (`disable: true`)，并且只注册 `wiki-` 前缀的自定义模式。
    *   在 MCP 服务和 FastAPI API 服务层更新权限判断规则，完美兼容并识别新前缀。

### 决策二：端侧（本地）与云端大模型分工架构设计
*   **背景**：针对 GraphRAG 框架在导入时需要多轮提取、在编译 Wiki 时 Token 消耗大、网速慢、API 费用高的痛点。
*   **具体修改**：
    *   确立了 **“端侧小模型干脏活，云端最强模型做参谋”** 的混搭架构。
    *   产出了 [docs/model-guide.md](./model-guide.md) 指南。
    *   **职责分工**：
        1.  **向量化 (Embedding)**：完全移至本地（如使用 `bge-small-zh-v1.5`）以降低成本。
        2.  **知识特征提取 (Extraction)**：使用本地小模型（如 `qwen2.5:7b` 跑在 Ollama）或高性价比云端 API（`gpt-4o-mini`），降低 Ingest Token 开销。
        3.  **问答推理 (QA Answer)**：使用云端最强智商模型（如 `Claude-3.5-Sonnet` / `GPT-4o`）。
        4.  **全局维基生成 (Wiki Page Compilation)**：使用超长上下文模型（如 `Gemini-2.5-Pro`）。

### 决策三：后端多模型配置管理器 (`llm_client.py`)
*   **背景**：在 `model-guide.md` 设计完毕后，为了支撑系统真正实现对多模型的动态解析和自动分流。
*   **具体修改**：
    *   新建 [llm_client.py](../softwiki/intelligence/llm_client.py) 模块，支持读取 `configs/model_profiles.yaml` 配置文件。
    *   解析包含 `openai`、`gemini`、`google`、`ollama` 在内的各种 Provider。
    *   实现 API 基础路径 (`base_url`) 和密钥的自动组装适配。

### 决策四：异步延迟提取流水线 (Asynchronous Lazy Extraction)
*   **背景**：之前 Ingest 文档时需要同步等待 Claim/Graph/Timeline 提取完毕才返回，导致上传一个 PDF 需要卡顿十几秒甚至几分钟，体验极差。
*   **具体修改**：
    *   在 `Document` 数据库表中增加 `status` 状态字段（`pending`, `extracting`, `completed`, `failed`）。
    *   引入自动 SQLite 迁移代码，兼容已有旧数据库。
    *   在 Ingest 时立刻进行切片、本地向量化和 BM25 索引构建，用户可立刻利用传统 RAG 检索。
    *   通过 Python `threading` 启动后台守护线程，异步去跑需要调用 LLM 的三项提取器，执行完毕后静默将状态更新为 `completed`。

### 决策五：增量 Wiki 编译与更新 (Incremental Wiki Compilation)
*   **背景**：随着文献库的变大，全量重构 Wiki 页面的 Token 消耗呈指数级上升。
*   **具体修改**：
    *   重构 `WikiPageGenerator`，引入增量 Diff-Patch 更新逻辑。
    *   生成 Wiki 时同时生成 `[topic_id].json` 记录所有已被处理的 Claims ID。
    *   当新增文献再次触发该主题的 Wiki 编译时，系统比对数据库与 JSON 文件，挑出“新增加的 Claims 和 Timeline 事件”，并将“原有 Wiki Markdown 文本” + “新增事实”一起喂给大模型，指示其进行原地修补（Incremental Update/Patch），避免全量重构的昂贵开销。
