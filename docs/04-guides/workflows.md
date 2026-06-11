# 研究工作流

SoftWiki 提供几种预设工作流，覆盖从快速问答到深度百科编译的不同场景。

## research 深度研判流

多查询 → 对比观点 → 综合简报

1. 分析问题，拆解为多个子查询。
2. 使用 websearch/webfetch 获取各维度的来源，横向对比不同来源的观点。
3. **[wiki-admin / wiki-manage 模式]** 对每个高质量来源检查 scope（参见 `config/scope.md`）。在范围内则调用 `softwiki_ingest` 摄入。
4. **[wiki-admin / wiki-manage 模式]** 摄入完成后，询问用户是否重 build 受影响的百科页面（`softwiki_wiki_build`）。
5. **[wiki-work 模式]** 若发现有价值来源，使用 `submit` 工作流预提交给管理员审核。
6. 输出结构化研究摘要，附带引用。

## wiki-compile 百科编译流

收集证据 → 识别共识/分歧 → 生成文档

1. 调用 `softwiki_status` 确认工作区存在相关文档。
2. 使用 websearch 查找缺失上下文或最新进展。
3. 若发现新的相关来源，先 `softwiki_ingest` 摄入。
4. 调用 `softwiki_wiki_build` 生成 markdown 百科页面。
5. 报告编译页面的输出路径。

## simple-q&a 快速问答流

单次混合查询（知识库 + 网络）

1. 直接使用已有知识或通过 websearch 获取最新信息回答。
2. **[wiki-admin / wiki-manage 模式]** 若发现高质量且在范围内的来源，询问用户是否摄入。

## contribute 知识贡献流

1. 调用 `softwiki_ingest` 摄入提供的 URL、文件或笔记。
2. 确认摄入结果并返回文档 ID。
3. 识别 `config/topics.yaml` 中可能受影响的主题。
4. 为每个受影响主题执行 `softwiki_wiki_build`。

## submit 提交审核流（wiki-work 专属）

用于 `wiki-work` 角色：将研究成果或来源提交给管理员审核，**不直接修改**知识库。

1. 汇总研究发现或在 session output 目录写结构化笔记。
2. 笔记包含：来源 URL、对工作区主题的相关性、关键发现、建议更新的百科页面。
3. 告知用户提交已暂存，等待 `wiki-manage` 或 `wiki-admin` 用户审核。
4. **不要调用** `softwiki_ingest`。**不直接修改**知识库。

---

## 摄入 → 索引 → 问答 → Wiki 完整示例

```bash
# 1. 摄入：从 URL 导入文档
./sw ingest --url "https://example.com/de-dollarization-overview"

# 2. 索引：构建向量与关键词索引
./sw index

# 3. 问答：基于知识库提问
./sw ask "核心发现是什么？"

# 4. 编译百科：生成结构化 Wiki 页面
./sw wiki build --topic de-dollarization
```

## Shell 内工作流

在 **Admin** / **Manage** 模式下，Shell 自动按以下循环工作：

```
research → ingest → wiki build → (loop)
```

即：用 websearch 做研究 → 摄入高质量来源 → 编译/更新百科页面 → 回到研究。
该循环无需手动切换模式，系统会基于对话上下文自动推进。

---

> **注意**：CLI 完整命令参考见 [CLI 文档](../03-operations/cli.md)。此处仅展示工作流层面的交互逻辑。
