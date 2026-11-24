# Claim × Graph × LLM-Wiki 联合检索（CGW）

> 状态：🚧 讨论中（P0 已实现，待评审后 freeze）
> 目标：让 graph 真正参与回答，而不是「关键词 LIKE 的装饰」；三者分工明确、互相补位。

---

## 1. 问题

现状（`softwiki/intelligence/answer_engine.py`）：

| 层 | 现状 | 问题 |
|---|---|---|
| Claim | 对 `canonical_claims.text` 做 `LIKE` | 中文问题无分词 → 命中 0 或不加过滤地返回前 12 条 |
| Graph | LightRAG 优先，失败退化为 `LIKE` + `limit 10` 无排序 | 中文命中 0；无实体链接、无跳数、无排序 |
| Wiki | 用问题串去匹配文件名 | 只有问题里出现 topic slug 才会命中 |
| RAG | 向量 + BM25 + RRF | 唯一正常工作的检索 |

结论：**图数据已经存在（实体/关系/claim 投影），但没有被“用”起来。**

## 2. 分工（本设计的核心）

| 层 | 角色 | 提供什么 | 不做什么 |
|---|---|---|---|
| **Graph** | 路由 / 结构 | 实体链接、1–2 跳邻域、路径、把 claim 与实体/文档挂起来 | 不产生事实，不做最终断言 |
| **Claim** | 事实源 | 原子事实、状态（active/disputed）、证据、页码、冲突 | 不负责找上下文 |
| **LLM-Wiki** | 叙事层 | 已编译的主题页：summary、边界、冲突小节 | 不覆盖 claim，不引入新事实 |
| RAG chunk | 原文证据 | 原始段落 + 页码 | 不做结构化 |

一句话：**Graph 决定「看哪里」，Claim 决定「什么是真的」，Wiki 决定「怎么讲」，RAG 提供「原文」**。

## 3. 检索流程（P0）

```
question
  │
  ├─ 1. 实体链接（Graph）
  │     归一化（NFKC/lower/去掉 - _ /）→ 与 Entity.name 双向子串匹配
  │     打分：名字长度 + 命中位置 + 实体度数
  │
  ├─ 2. 邻域扩展（Graph）
  │     BFS 1–2 跳（按 source_name/target_name 字符串，P0 不改 schema）
  │     收集边：hop、confidence、document_id、canonical_claim_id
  │
  ├─ 3. 事实挂载（Claim）
  │     a) 边上的 canonical_claim_id → CanonicalClaim（active/disputed）
  │     b) 种子实体 subject/object 命中的 canonical claims
  │     c) 未挂 claim 的边 → 同文档 raw claims（低权重兜底）
  │     去重 + 排序：图距离、边置信度、claim 置信度、evidence_count、时效
  │
  ├─ 4. 叙事匹配（Wiki）
  │     种子实体 → wiki pages index → 仅取非 stale 页面 → 截断摘要
  │
  └─ 5. 融合输出（结构化，交给 AnswerEngine 拼 prompt）
        paths:   M55 --implements--> Helium (1 hop, conf 0.90)
        claims:  带状态/证据数/页码/冲突标记
        wiki:    主题摘要
```

### 3.1 降级

- 链接不到实体 → 返回空，AnswerEngine 退回原有 RAG/文本检索；
- Graph 模块关闭 → 完全不调用；
- Wiki 页面 stale / 不存在 → 跳过，不影响 claim 与 RAG；
- 任何异常只记录日志并降级，不阻断回答。

### 3.2 引用与冲突

- claim 引用来自 `CanonicalClaim.primary_document_id` + `primary_page_start/end`；
- 边引用来自 `Relationship.document_id`；
- `status=disputed` 的 claim 必须显式标注，且与冲突对象一起展示，**不允许静默选边**；
- 排除 `status` 非 active/disputed 的 claim（error/superseded）。

## 4. 决策记录

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | Graph 只做路由，事实仍以 Claim 为准 | 保持「claim 为事实源，图/时间线/Wiki 为投影」的项目原则 |
| D2 | P0 不改 schema，用名字做边遍历 | 先把链路跑通并量化；实体 ID 化（P1）需要回填与别名合并，风险独立 |
| D3 | Wiki 页只在非 stale 时参与 | 避免用旧叙事覆盖新事实；stale 由既有 `WikiArtifactState` 判断 |
| D4 | 实体链接先做确定性匹配（归一化 + 子串 + 度数） | 不引入额外 LLM 调用；可测、可解释、零成本 |
| D5 | 冲突必须显式呈现 | 与 `knowledge-system-philosophy.md` 一致 |
| D6 | 排序用可解释的加权和，不训练 ranker | 数据量小（万级边），先要可调可解释 |

## 5. 已知限制 / P1+

- 边端点是字符串：`ARM` / `Arm` / `ARM Ltd.` 仍是不同实体 → 需要 `source_entity_id`/`target_entity_id` + 别名表；
- 关系盲插未去重，`confidence` 恒 1.0 → 需要合并与质量分；
- 实体链接是 O(N) 扫描（万级可接受，十万级需要倒排/向量）；
- 没有评测集 → P1 建 20–30 条 golden questions（含期望实体/路径/引用），对比 graph on/off；
- Wiki 只按 subject 匹配，尚未按边/claim 反查页面。

## 6. 验收（P0）

1. 中文问题能命中实体并产出图上下文（现状为 0）；
2. 图上下文带跳数/置信度/引用，按相关性排序而非插入顺序；
3. 图挂到的 canonical claim 进入 claims 上下文且去重；
4. stale wiki 不参与；
5. 无命中时行为与现状一致（降级不回归）；
6. `tests/test_graph_claim.py` 覆盖以上各点。
