# 知识系统实现计划（Claim / 冲突 / Graph / LLM-Wiki）

> status: 🚧 讨论中（2026-10-25）
> 原则文档：`docs/02-design/knowledge-system-philosophy.md`
> 目标：把当前“按文档并行的抽取结果”升级为“以 Claim 为中心、可去重、可版本化、可人工裁决、可投影”的知识系统。
> 术语：**LLM-Wiki** 是叙事层；**WikiArtifact / WikiArtifactState** 是页面工件；**Static Wiki Site** 是发布层，三者不是一回事。

---

## 0. 当前基线

```text
docs:                  73
chunks:                39,870
claims:                10,573
entities:              4,165
relationships:         7,211
events:                639
duplicate claim-text groups: 353 / 1,491 extra rows
duplicate chunk-text groups: 55 / 62 extra rows
curated wiki pages:    12
claim coverage:        15.94%（effective 17.80%）
```

当前缺口：

- 无 `document_family_id` / `revision` / `supersedes_document_id`
- 无 `ClaimEvidence`
- 无 claim `status` / `valid_from` / `valid_to`
- 无 `Contradiction` / `Adjudication`
- Graph 与 Claim 并行抽取，无关联
- Wiki 手动生成，无 stale/自动重建
- 无冲突感知的 AnswerEngine

---

## 1. 难度定义

| 等级 | 含义 | 粗估 |
|---|---|---|
| S | 单模块、低风险 | 1–2 天 |
| M | 多模块、需迁移/联调 | 3–6 天 |
| L | 跨 schema/pipeline/UI | 7–12 天 |
| XL | 跨系统、需大规模迁移/评测 | 12 天+ |

> 粗估按 1 名熟悉代码的工程师；实际取决于数据迁移与评审。

---

## 2. 工作流拆解与难度

### A. Knowledge Schema v2

- [x] `Document`: `family_id`, `revision`, `supersedes_document_id`, `document_hash`
- [x] `Claim`: `canonical_id`, `canonical_key`, `status`, `valid_from`, `valid_to`, `value_normalized`
- [x] `ClaimEvidence`: `claim_id`, `canonical_id`, `document_id`, `page_start`, `page_end`, `quote`, `source_revision`, `trust_level`
- [x] `Contradiction`: `claim_a_id`, `claim_b_id`, `type`, `severity`, `status`, `auto_resolved`, `resolution`
- [x] `Adjudication`: `contradiction_id`, `action`, `before_json`, `after_json`, `actor`, `reason`, `created_at`
- [ ] `WikiArtifactState`: `topic`, `prompt_version`, `model`, `claim_set_hash`, `status_counts`, `built_at`, `stale_at`
- [x] 迁移脚本；SQLite/PG 双支持

**难度：L（8–12d）**  
**依赖：无**  
**风险：迁移 10,573 claims；必须保留 raw claim，不删除。**

---

### B. Ingestion / Versioning

- [x] 完全重复：hash + URL（已有）
- [x] 同 URL 内容变化：新版本，不 skip
- [x] `family_id` 识别：URL / source+title / 显式输入
- [x] `revision`：published_at / 显式字段 / 手工覆盖（v0）
- [x] `supersedes_document_id`
- [x] 旧文档不删除；新文档继承 family

**难度：M（4–6d）**  
**依赖：A**  
**风险：PDF revision 不稳定；需要手工覆盖入口。**

---

### C. Claim Canonicalization v1

- [x] normalized text（空白/标点/页眉页脚）
- [x] canonical key：`(normalized_text, actor, topic, stance)`
- [x] 同一 key → 一条 canonical claim + 多条 evidence
- [x] 合并 confidence（max）
- [x] 保留 raw claim 用于审计
- [x] 对现有冗余做一次性回填（807 merged）
- [x] 不做矛盾合并

**难度：L（8–12d）**  
**依赖：A**  
**风险：canonical key 过粗会误合并；先确定性规则，后 LLM 结构化。**

---

### D. Version Supersede（自动）

- [x] 同 family + 新 revision + 同模板/不同值（v0）
- [x] 旧 claim → `superseded`；新 claim → `active`
- [x] `supersedes` 关系 + 自动 `Contradiction`
- [x] 审计（Adjudication）+ reopen
- [x] 人工“保留双方”优先于自动

**难度：M（4–6d）**  
**依赖：A/B/C**  
**风险：revision 误判；必须有 family/revision 置信度。**

---

### E. Conflict Detection

P0 规则：

- [~] 同模板 + 不同单值（v0 保守；真实库 0）
- [~] 数值/寄存器值（v0；日期/位宽未覆盖）
- [~] 同模板/单值（v0）
- [x] 同文档/跨文档
- [x] severity：high/medium（v0）

P2 语义：

- [ ] embedding 相似 + NLI/LLM judge
- [~] 版本/来源上下文（v0）；时间未覆盖
- [ ] 误报评测集

**难度：L（规则 8–12d；NLI 另 8–12d）**  
**依赖：C**  
**风险：规则覆盖有限；NLI 误报/成本。**

---

### F. Human Adjudication

- [x] `POST /api/conflicts/{id}/adjudicate`
- [x] 动作：accept A/B、keep both、mark error、needs evidence、reopen（merge/split 未做）
- [x] 事务：claim status + contradiction + audit
- [~] 权限：demo 阶段 admin 单用户
- [x] 冲突队列 API
- [x] 最小审核 UI（Sidebar Conflicts）
- [x] 裁定后标记相关 Wiki stale

**难度：M（5–8d）**  
**依赖：A/E**  
**风险：并发裁定；需要乐观锁/版本号。**

---

### G. AnswerEngine 冲突感知

- [x] 只取 `active` claims
- [x] `disputed` 并列展示
- [~] `superseded` 默认排除；历史问题未做
- [~] 引用带 status/source/date/page；revision 部分
- [x] 冲突未裁决时明确说“存在冲突”
- [x] 不静默选一个

**难度：M（4–6d）**  
**依赖：A/C/E**  
**风险：prompt 需约束，不能只靠检索。**

---

### H. Graph 投影

- [~] GraphEdge 挂 `canonical_claim_id` / status 列；回填未做
- [~] status 列 + 查询过滤；版本继承未做
- [ ] 关系型 claim → triple → edge
- [ ] 属性型 claim 不进图
- [ ] Entity resolution（CM55 / Cortex-M55）
- [ ] GraphExtractor prompt 改 ARM 技术关系
- [x] 查询只返回 active

**难度：L（6–10d）**  
**依赖：C**  
**风险：现有 7,211 关系需要回填/重建；LightRAG 索引与 canonical graph 要区分。**

---

### I. Timeline 投影

- [~] Event 挂 canonical_claim_id / status 列；回填未做
- [~] status 列 + 查询过滤；版本未做
- [ ] 时间冲突/版本差异
- [x] Timeline UI 保留；status 过滤

**难度：M（3–5d）**  
**依赖：A/C**  
**风险：事件日期抽取质量。**

---

### J. LLM-Wiki 状态与重建

- [ ] `WikiArtifactState`：claim hash / prompt version / status counts / stale
- [x] `stale` 事件：claim 变化/裁定
- [ ] 重建队列（单页/批量）
- [~] 手动单页/全量；增量未做
- [ ] 页面 Current / History / Disputed 结构
- [x] stale 页面不参与权威回答

**难度：M（4–6d）**  
**依赖：A/C**  
**风险：重建成本；必须限流/队列。**

---

### K. Wiki 规模策略

- [~] Tier 1 策展 12 页；100–300 未做
- [ ] Tier 2 on-demand（缓存）
- [~] Tier 3 只检索；策略未固化
- [x] 单页 claim 上限 250
- [~] 三级分类；IP 子页未做
- [ ] usage/coverage 优先级
- [ ] 后台批处理

**难度：M（4–6d）**  
**依赖：J**  
**风险：curated map 维护；按需页质量。**

---

### L. Near-duplicate Documents（P2）

- [ ] SimHash/MinHash/embedding
- [ ] `duplicate_of_document_id`
- [ ] 不重复抽取
- [ ] 保留 occurrence

**难度：L（8–12d）**  
**依赖：A**  
**风险：误判；阈值校准。**

---

### M. Chunk Dedup（P1）

- [ ] normalized chunk hash
- [ ] canonical chunk + occurrence
- [ ] 检索折叠重复/重叠
- [ ] MMR/多样性

**难度：M（3–5d）**  
**依赖：A**  
**风险：检索质量回归；需评测。**

---

### N. Metrics / Evaluation

- [x] duplicate doc/claim rate（metrics）
- [x] canonical claim count
- [x] conflict count by type/severity
- [x] auto-resolved vs pending
- [ ] review SLA
- [~] wiki stale count；coverage 已有
- [ ] answer conflict compliance
- [~] synthetic tests；黄金集未做

**难度：S（2–3d）**  
**依赖：A/C/E/J**  
**风险：指标定义要先固定。**

---

## 3. 阶段计划

### P0 — 事实层可裁决（约 43–65 人天；1 人 9–13 周，2 人约 5–7 周）

目标：Claim 成为事实源，重复可合并，版本可自动，来源冲突可人工。

1. A Schema v2（L）
2. B Ingestion/versioning（M）
3. C Claim canonicalization v1（L）
4. D Version supersede（M）
5. E 规则冲突检测（L，先做数值/寄存器/日期）
6. F 人工裁定 API/最小 UI（M）
7. G AnswerEngine 冲突感知（M）
8. N 指标（S）

**验收：**

- 1,491 冗余 claim 行 → canonical claim + evidence，无数据丢失
- 合成 v1/v2 文档 → 自动 supersede
- 同期来源冲突 → pending review；答案并列显示
- 人工裁定 → 状态/审计/缓存失效
- AnswerEngine 不再静默选一个

### P1 — 投影层可控（约 21–33 人天；1 人 4–7 周，2 人约 3–4 周）

1. H Graph 挂 claim/evidence/status（L）
2. I Timeline 挂 claim/evidence（M）
3. J Wiki state/stale/rebuild（M）
4. M Chunk dedup（M）
5. K Wiki 规模策略（M）

**验收：**

- Graph 查询只返回 active
- 冲突/版本变化 → Wiki stale → 重建
- Wiki 显示 Current / History / Disputed
- 12 页 → 稳定策展层

### P2 — 大库与自动化（约 16–27 人天；1 人 3–6 周）

1. L Near-duplicate docs（L）
2. E NLI/LLM 冲突检测（L）
3. 自动文档家族/revision（M）
4. 冲突严重度评分（M）
5. 成本/队列/限流优化（M）

---

## 4. 依赖图

```text
A Schema
  ├─ B Versioning
  ├─ C Canonicalization
  │    ├─ D Supersede
  │    ├─ E Conflict
  │    │    └─ F Adjudication
  │    ├─ H Graph
  │    ├─ I Timeline
  │    └─ J Wiki state
  │         └─ K Scale
  └─ L Near-dup
       └─ M Chunk dedup
G AnswerEngine depends on A/C/E
N Metrics depends on A/C/E/J
```

---

## 5. 关键风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| PDF revision 不可靠 | 版本误判 | 手工覆盖 + family 置信度 |
| canonical key 过粗 | 误合并 | 先确定性规则，后 LLM 结构化 |
| 冲突误报 | 审核过载 | 规则优先 + severity + 评测集 |
| 迁移 10,573 claims | 数据风险 | 备份 + 双写/影子表 + 可回滚 |
| Graph 重建 | 7,211 关系 | 先双写，再切读 |
| Wiki 重建成本 | 延迟/费用 | 队列 + 限流 + 只重建 stale |
| stale Wiki 参与回答 | 错误 | 状态过滤 + 回退 claim |
| 人工审核瓶颈 | 积压 | 分级 + 自动版本 supersede |

---

## 6. 迁移策略

1. 备份 PostgreSQL（`pg_dump`）
2. 新增表/字段，不删除旧字段
3. 回填 `ClaimEvidence`：`document_id` + chunk page/quote
4. 回填 canonical claim：确定性 key
5. 双写：旧 claim + canonical claim
6. 影子读：AnswerEngine 可切换
7. 对比指标：答案一致率/覆盖/冲突
8. 切读；保留回滚开关

---

## 7. 建议的下一步

先做 **A + C + E(规则 v0) + F + G** 的纵向切片：

- Schema v2
- Canonical claim v1
- 最小裁定 API
- 冲突感知 AnswerEngine

这是最小可验证闭环：**重复可合并、冲突可发现/审核、答案不静默选一个。**

然后再做版本自动 supersede 和 Graph/Wiki 投影。

---

## 8. v0 实施记录（2026-10-30）

- Schema：`CanonicalClaim` / `ClaimEvidence` / `Contradiction` / `Adjudication` / `WikiArtifactState`；Document/Claim/Relationship/Event 新列。
- 迁移脚本：`scripts/knowledge_v2_migrate.py`、`scripts/knowledge_v2_rescan.py`、`scripts/knowledge_v2_wiki_states.py`。
- 数据：10,573 raw claims → 9,766 canonical + 10,573 evidence；807 merged；当前 0 open conflicts（保守模板规则）。
- API：`/api/knowledge/metrics`、`/api/conflicts`、`/api/conflicts/scan`、`/api/conflicts/{id}/adjudicate`、`/api/canonical-claims`、`/api/canonical-claims/{id}/evidence`。
- UI：Sidebar **Conflicts**；accept A/B、keep both、mark error、needs evidence、reopen；Wiki stale banner。
- AnswerEngine：canonical active/disputed + conflict context + 不静默选边。
- 12 个策展 Wiki 页面标记 stale；重建后 state 清除 stale。
- 备份：`/tmp/armkb_before_knowledge_v2.sql`（116MB）。
- 未完成：Graph/Timeline claim 回填、chunk dedup、Wiki 重建队列/自动重建、NLI/近重复文档。

---

## 9. 工作量粗估

| 工作流 | 难度 | 粗估 |
|---|---|---|
| A Schema | L | 8–12d |
| B Versioning | M | 4–6d |
| C Canonicalization | L | 8–12d |
| D Supersede | M | 4–6d |
| E Conflict rules | L | 8–12d |
| F Adjudication | M | 5–8d |
| G AnswerEngine | M | 4–6d |
| H Graph | L | 6–10d |
| I Timeline | M | 3–5d |
| J Wiki state | M | 4–6d |
| K Wiki scale | M | 4–6d |
| L Near-dup docs | L | 8–12d |
| M Chunk dedup | M | 3–5d |
| N Metrics | S | 2–3d |

总计约 **70–110 人天**（1 人，可并行压缩）；P0 纵向切片约 **35–53 人天**。
