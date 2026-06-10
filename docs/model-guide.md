# Softwiki 模型配置与选型指南 (Model Selection & Configuration Guide)

**更新日期**：2026-06-09

在 Softwiki 系统的架构中，“**原始文献为唯一证据源**”的严谨学术原则决定了系统需要进行大量的多维特征抽取与知识融合。为了在**检索精度**、**系统延迟**、**数据安全隐私**以及 **Token 成本**之间取得最佳平衡，系统对不同应用场景所需的模型进行了精细化的解耦。

本指南旨在指导用户如何针对 Softwiki 的核心场景进行合理的模型选型与配置。

---

## 1. 模型应用场景矩阵 (The LLM Scenarios)

Softwiki 共有五个场景需要调用 AI 服务：

| 使用场合 | 运算频次 | 智力要求 | 上下文需求 | 推荐模型 |
| :--- | :--- | :--- | :--- | :--- |
| **① 向量化 (Embedding)** | 极高（每个分块） | 无 | 短（~512 token） | 本地轻量模型 / 廉价云端 API |
| **② 知识提取 (Extraction)** | 高（每篇文献多次） | 中等（严格 JSON 输出） | 中等（~15k 字符） | 端侧小模型 / 高性价比云端小模型 |
| **③ 智能问答 (Answer Engine)** | 中（每次用户提问） | 极高（跨文献深度推理） | 中至长 | 顶级推理模型 |
| **④ Wiki 编译 (Wiki Page)** | 低（后台异步） | 极高（大局观 + 文笔） | 超长 | 最强模型 + 超长上下文 |
| **⑤ Shell Agent** | 中（交互会话） | 高（任务规划 + 工具调用） | 中 | 独立配置（与 Core 解耦） |

---

## 2. 核心场景选型建议 (Deep Dive into Scenarios)

### ① 向量化 (Embedding)
*   **任务目标**：将清洗切片后的 Chunks 转换为高维向量，存入本地向量检索库。
*   **选型痛点**：这是纯粹的数学向量映射，**不需要模型具备任何逻辑思考能力**。如果使用昂贵的云端 API，会产生大量的冗余费用。
*   **推荐方案**：
    *   **本地（推荐）**：使用 `bge-small-zh-v1.5`（中文环境优选）或 `all-MiniLM-L6-v2`（英文环境优选）。这些模型只有几十到一百多 MB，可以在本地 CPU 上实现秒级极速向量化，费用为 0。
    *   **云端**：使用 OpenAI 的 `text-embedding-3-small`，价格极其低廉。

### ② 知识提取 (Extraction)
*   **任务目标**：从导入的文献中榨取图谱（实体与关系）、立场表态（Claims）以及时序线索（Timeline）。
*   **选型痛点**：这是大批量处理文献的阶段。模型需要严格输出 JSON 格式。如果选用 GPT-4o 等顶级模型，Token 账单会非常高昂。
*   **推荐方案**：
    *   **本地（推荐）**：通过 Ollama 在本地部署 `Qwen-2.5-7B-Instruct` 或 `Llama-3.1-8B-Instruct`。它们对 JSON 格式的遵循度非常好，且在本地显卡跑不用花一分钱。
    *   **云端**：选用 `gpt-4o-mini` 或 `gemini-2.5-flash`。这类高性价比 mini 模型单次提取成本仅为顶级模型的十几分之一。

### ③ 智能问答 (Answer Engine)
*   **任务目标**：在 `ChatPanel` 实时回答用户的学术提问，将 RAG 切片、图谱三元组、立场矩阵、时间线和 Wiki 整合为事实报告，并给出置信度评估。
*   **选型痛点**：用户的问题可能是跨文献的复杂比对（例如：“文献 A 和文献 B 在这个时间点上的冲突立场是什么？”）。这极度考验模型的**逻辑严谨性与“Lost in the Middle”的抗干扰能力**。
*   **推荐方案**：
    *   **本地**：若本地硬件充裕，可部署 `Qwen-2.5-14B-Instruct` 或 `Qwen-2.5-32B-Instruct`。
    *   **云端（推荐）**：首选 `Claude-3.5-Sonnet` 或 `GPT-4o`。顶级模型给出的分析深度、引文精确度有质的差距。

### ④ 维基编译 (Wiki Page)
*   **任务目标**：将数据库中累积的大量碎裂事实、图谱和 Claim 合成为人类可读、逻辑连贯的 markdown 页面（`llm-wiki.md`）。
*   **选型痛点**：因为是多文献的全局合成，喂给模型的上下文非常长，且非常考验模型的**“大局观”和文笔**。
*   **推荐方案**：
    *   **云端**：首选 **`Gemini-2.5-Pro`**（其拥有 200万 Tokens 的超大上下文，可以将所有关联的图谱和段落一次性装入），或选用 `Claude-3.5-Sonnet` 获得极佳的文笔与组织结构。

---

## 3. 典型配置方案 (Deployment Recipes)

### 方案 A：完全本地化/端侧部署 (100% Offline & Private)
> [!IMPORTANT]
> **适用场景**：涉及高机密文件（如军工、绝密专利、未发表的政策草稿等），或在无公网网络的环境下使用。
*   **向量化 (Embedding)**：本地加载 `bge-small-zh-v1.5`
*   **知识提取 (Extraction)**：Ollama 运行 `qwen2.5:7b`
*   **智能问答 (QA Reasoning)**：Ollama 运行 `qwen2.5:14b` 或 `qwen2.5:32b`
*   **维基编译 (Wiki Compilation)**：Ollama 运行 `qwen2.5:14b` 或 `qwen2.5:32b`

### 方案 B：高性价比混搭部署 (Cost-Effective Hybrid) - ⭐ 强烈推荐
> [!TIP]
> **适用场景**：学术研究人员日常使用。既要控制 Token 账单，又要追求在问答和维基生成时的极致质量。
*   **向量化 (Embedding)**：本地加载 `bge-small-zh-v1.5`（免费、快）
*   **知识提取 (Extraction)**：Ollama 运行 `qwen2.5:7b`（本地干粗活，免费）
*   **智能问答 (QA Reasoning)**：云端调用 `Claude-3.5-Sonnet` 或 `Gemini-2.5-Flash`（高响应、高智力）
*   **维基编译 (Wiki Compilation)**：云端调用 `Gemini-2.5-Pro`（200万长上下文，大局观强）

---

## 4. 配置文件配置参考 (Configuration File Template)

用户可在工作区的 `configs/model_profiles.yaml` 中进行如下混搭或本地配置：

```yaml
# configs/model_profiles.yaml

profiles:
  # 向量模型配置
  embedding:
    provider: "local" # 选项: local, openai
    model: "bge-small-zh-v1.5" # 对应本地加载的模型名称
  
  # 批量特征榨取配置（Ingest 阶段使用）
  cheap_extraction:
    provider: "ollama" # 选项: ollama, openai, gemini
    model: "qwen2.5:7b"
    api_base: "http://localhost:11434/v1"
    temperature: 0.0
    max_tokens: 2048

  # 智能问答配置（Chat 阶段使用）
  qa_reasoning:
    provider: "openai" # 选项: openai, gemini, ollama
    model: "gpt-4o"
    api_base: "https://api.openai.com/v1"
    temperature: 0.2

  # 全局维基编译配置（Build Wiki 阶段使用）
  wiki_compilation:
    provider: gemini
    model: gemini-2.5-pro
    api_base: "https://generativelanguage.googleapis.com/v1beta/"
    temperature: 0.3
    max_tokens: 8192
```

通过这套配置机制，Softwiki 可以无缝在"学术免费版（本地全开）"与"商业级研究专家版（混搭大模型）"之间自由切换。

---

## 5. Shell Agent 模型（独立配置）

Shell TUI 使用 opencode 作为 AI 引擎，其模型**独立于 Core LLM**，通过以下环境变量配置：

```bash
# Shell 独立模型配置（优先于 Core 的 ANALYSIS_MODEL）
SHELL_MODEL=gemini-2.5-flash
SHELL_API_BASE=https://generativelanguage.googleapis.com/v1beta/
SHELL_API_KEY=your_shell_api_key
```

**优先级**：`SHELL_MODEL` > `ANALYSIS_MODEL` > `"gemini-2.5-flash"`（默认）

Shell 的 web search 使用 opencode 原生的 `websearch/webfetch` tools，走模型自带的搜索能力（Gemini Search Grounding、Claude 搜索等），**无需额外 API key**。
