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

---

## 7. v2 实施记录（2026-11-24）

P0 只证明链路能跑；v2 解决数据质量与可演示性：

| 项 | v2 做法 | 代码 |
|---|---|---|
| 抽取 prompt | ARM 领域：实体类型 taxonomy、canonical 名称、aliases、受控关系词、confidence、证据短语；端点必须是本窗口抽到的实体 | `extraction/graph_extractor.py` |
| 实体归一 | `entities.normalized_name` + `entity_aliases` + `merged_into`；同名（大小写/标点/公司后缀）确定性合并，不删行 | `graph/resolution.py`、`scripts/graph_normalize.py` |
| 边端点 | `relationships.source_entity_id` / `target_entity_id`，遍历优先用 id，名称仅兜底 | 同上 |
| 边权重 | 按 (source, target, relation_type) 统计 distinct 文档数 → `weight`；`evidence_count` 为行数 | `scripts/graph_normalize.py` |
| 检索 | 实体链接走 normalized + alias；排序 hop + confidence + `log(1+weight)` | `intelligence/graph_claim.py` |
| API | `/api/graph/search`、`/api/graph/entity`、`/api/graph/path`；subgraph 支持 id | `api/server.py` |
| 演示 | `/graph-studio`：力导向图、搜索、路径高亮、实体卡、claim 徽章、wiki 摘要 | `web/app/graph-studio/` |
| 验收 | `scripts/graph_acceptance.py` + `scripts/graph_golden.yaml`：实体命中率、术语覆盖（CGW vs 旧 LIKE）、p50/p95 | 同上 |
| 批量重抽 | `scripts/graph_reextract.py`：多文档并行抽取 → 串行 canonicalize → 孤儿清理 → 归一 | 同上 |
| 抽取并发 | 所有窗口的 3 个抽取器一次性提交（`EXTRACTION_WINDOW_CONCURRENCY`），DB 写入仍串行 | `extraction/processor.py` |

**新增决策**

| 编号 | 决策 | 理由 |
|---|---|---|
| D7 | 先重抽再归一，不在旧数据上打补丁 | 旧 prompt 抽出的实体类型/关系词不可用；重抽后用新别名重建别名表 |
| D8 | 归一只做确定性合并（normalized 相同或显式 alias） | 模糊合并会不可逆地毁掉实体；宁可少合并 |
| D9 | 保留每个文档的边行，用 `weight` 表达跨文档强度 | 删行会丢引用；权重让检索排序表达“多文档佐证” |
| D10 | 演示页独立路由 `/graph-studio` | 不干扰日常 WebUI；可全屏投屏 |

**验收基线（armkb，重抽后重跑）**

```
python scripts/graph_acceptance.py --runs 5 --json /tmp/armkb_graph.json
```

看四个数：entity_link_rate、avg_term_coverage（CGW vs baseline）、avg_claims/edges、latency p50/p95。

**armkb 实测（2026-11-24，73 篇重抽后）**

| 指标 | 结果 |
|---|---|
| golden questions | 24 |
| 实体链接命中率 | **100%** |
| 术语覆盖（CGW） | **82.0%** |
| 术语覆盖（旧 LIKE 基线） | 40.3% |
| 平均图上下文 | 80 条边 / 16 条 canonical claim |
| 检索延迟 | **p50 62 ms / p95 79 ms**（正则缓存 + 子串前置） |

数据规模变化（重抽前后）：

| | 重抽前 | 重抽后 |
|---|---|---|
| claims | 10,573 | **15,465** |
| canonical claims | 9,766 | **14,704** |
| entities | 4,165 | **9,256**（合并 634、别名 2,244） |
| relationships | 7,211 | **9,491**（8,957 已挂 claim；平均 weight 1.12） |
| events | 639 | 743 |

**504 补图（2026-11-24）**：首轮重抽约 16% 窗口 504 被跳过（关系 4,572）；
随后用 `scripts/graph_topup.py --all` 只重跑图抽取，关系数升到 **9,491**，
术语覆盖 77.8% → **82.0%**，检索延迟经正则缓存优化后 p50 从 502ms 降到 **62ms**。

### 图质量快照（armkb，2026-11-25 补图 + 归一后）

| 指标 | 数值 |
|---|---|
| active 关系 | 9,470 |
| 未挂 canonical claim | 534（5.6%） |
| 平均 weight | 1.117 |
| weight ≥ 2 | 729 |
| weight ≥ 3 | 167 |
| 最大 weight | 12（APB domain —part_of→ AMBA） |

解读：

- 绝大多数边只在一篇文档出现（weight=1），跨文档互证仍是少数；这与 73 篇手册
  各覆盖不同模块相符，不代表抽取错误；
- 534 条未挂 claim 的边集中在“泛化关系/表格行”上，`knowledge_v2_projections.py`
  的 Jaccard ≥0.12 阈值没有匹配到同文档 claim；降低阈值会提高挂载率但也会引入
  错配，暂不调整；
- 若要进一步提升，优先级是：① 实体别名继续收编（AXI4/ACE/AHB-Lite）；② 对
  weight≥3 的边人工抽检；③ 用 golden set 的 graph on/off 差异定位“挂错”的边。
