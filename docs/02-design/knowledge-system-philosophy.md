# 知识系统思想（Knowledge System Philosophy）

> status: ✅ frozen（原则层，2026-10-25）
> 本文记录 SoftWiki 的知识观、层间工作流、重复/冲突策略、LLM-Wiki 方法论与规模策略。
> 实现计划与难度见：`docs/05-roadmap/knowledge-system-plan.md`。

---

## 0. 第一原则

1. **Claim 是事实的最小可裁决单元。**
2. **Graph / Timeline / LLM-Wiki 都是 Claim 的投影，不是第二套事实源。**
3. **Wiki 可以重写、可以重建、可以换 prompt，但不能反过来成为事实。**
4. **自动只处理确定性变更；语义冲突必须人工。**
5. **原始文档不可变；所有干预落在 claim / evidence / status / 关系 / 审核记录上。**
6. **不删除历史；只标记状态。**

---

## 1. 分层模型

```text
Document（原始、不可变）
  │
  ├─ Chunk（检索片段）
  │
  └─ ClaimCandidate
        └─ CanonicalClaim（事实源）
             ├─ ClaimEvidence（文档/页码/原文/版本）
             ├─ RelationTriple → Graph（关系投影）
             ├─ EventRecord   → Timeline（时间投影）
             └─ WikiArtifact  → LLM-Wiki（叙事投影）
```

| 层 | 职责 | 事实源 |
|---|---|---|
| Document | 原始证据、可追溯 | 是（原文） |
| Chunk | 召回、上下文、向量/BM25 | 否 |
| Claim | 可验证断言、冲突、版本、审核 | **是** |
| Graph | 关系导航、影响分析 | 否，Claim 投影 |
| Timeline | 时间线、演进 | 否，Claim 投影 |
| LLM-Wiki | 人读叙事、入口、导航 | 否，Claim 投影 |

一句话：

> **Chunk 负责找得到，Claim 负责可裁决，Graph/Timeline 负责结构，LLM-Wiki 负责讲给人听。**

### 1.1 术语（避免混淆）

| 术语 | 含义 | 不是什么 |
|---|---|---|
| **LLM-Wiki** | Claim/Evidence 的叙事投影层 | 不是事实源 |
| **WikiArtifact** | 某个 topic 生成出的 Markdown + 状态 JSON 工件 | 不是静态 HTML 站点 |
| **WikiPanel** | WebUI 里的动态预览/编辑入口 | 不是站点生成器 |
| **Static Wiki Site** | 由 WikiArtifact 构建出的静态 HTML 站点（MkDocs/Docusaurus/Next export 等） | 不参与 claim/冲突/版本逻辑 |

当前代码中的 `WikiPageGenerator` 是 **WikiArtifact compiler**；`WikiPanel` 是动态 UI；目前还没有静态站点生成/发布层。

---

## 2. Claim 的概念

Claim 是“被声称的事实”，不一定为真。

```text
text          断言本身
actor         谁说的 / 谁的属性
topic         主题
stance        支持 / 谨慎 / 反对 / 不明确
confidence    抽取置信度
published_at  来源日期
document_id   来源文档
evidence      页码、原文、来源、版本
status        active / superseded / disputed / retracted
```

Claim 不是：

- Chunk（文本片段）
- Entity（节点）
- Relationship（边）
- Event（时间点事件）
- 摘要（概括）
- Wiki 段落（叙事）

Claim 是**可去重、可冲突、可版本化、可审核**的最小单元。

---

## 3. 完整数据流

### 3.1 入库

```text
Document
  ├─ exact hash / URL duplicate → skip
  ├─ version detection → family_id / revision / supersedes
  └─ raw immutable
```

- 完全重复：hash/URL 直接跳过
- 同 URL 内容变化：建新版本，不跳过
- 原始文档永不修改

### 3.2 抽取

```text
Document → windows → Chunk
                 └→ ClaimCandidate
                 └→ GraphCandidate（候选关系）
                 └→ EventCandidate
```

- Claim 抽取按窗口进行
- Graph/Event 是候选，不直接成为 canonical
- 每条 claim 必须能回到文档/页码/原文

### 3.3 规范化 / 压缩

这是知识系统的核心环节：

```text
ClaimCandidate
  → normalize
  → dedup / merge similar
  → version supersede
  → conflict detection
  → CanonicalClaim + ClaimEvidence
```

- 相同语义、相同上下文、相同值 → 合并为一条 canonical claim，多证据
- 版本更新 → 自动 supersede
- 来源冲突 → 标记 disputed，进审核
- 不删除旧 claim

### 3.4 投影

```text
CanonicalClaim
  ├─ RelationTriple → GraphEdge
  ├─ EventRecord   → TimelineEvent
  └─ WikiArtifact  → LLM-Wiki
```

投影可以重建；投影不反向覆盖 claim。

### 3.5 使用

```text
检索 / 问答 / Wiki / Agent
  → 只使用 active
  → disputed 必须并列展示
  → superseded 仅历史
  → retracted 排除
```

### 3.6 反馈

```text
使用
  → 缺口 / 冲突 / 覆盖不足 / 高频问题
  → 审核队列 / 补文档 / 调 taxonomy / 改 prompt
  → 再重建
```

**反馈的是策展信号，不是事实。**

---

## 4. 重复策略

### 4.1 输入层：完全重复

已实现：

- `cleaned_text` SHA-256
- URL duplicate
- 重复直接 skip

局限：

- 只认完全一致文本
- 改格式/页眉页脚/重新导出可能 hash 不同
- 同 URL 内容更新会被跳过，没有版本

### 4.2 文档层：近重复

目标：

- SimHash/MinHash 或 embedding 相似度
- `duplicate_of_document_id`
- 不重复抽取；保留来源 occurrence

### 4.3 Chunk 层：内容去重

- normalized chunk hash
- canonical chunk + occurrence `(document_id, page_start, page_end)`
- 检索折叠重复 chunk / 重叠页

### 4.4 Claim 层：canonical claim

Canonical key：

```text
(normalized_text, actor, topic, stance)
```

- 一条 canonical claim
- 多条 evidence
- 合并置信度
- 原始 claim 保留用于审计

### 4.5 重复 vs 冲突

```text
相同语义 + 相同上下文 + 相同值 → 合并
相同语义 + 不同值             → 冲突
不同 scope / revision         → 分开
```

**去重只合并“相同”；不合并“矛盾”。**

---

## 5. 冲突策略

### 5.1 四类冲突

| 类型 | 例子 | 处理 |
|---|---|---|
| 版本更新 | 2020 手册 0x0，2024 手册 0x1 | 自动 supersede |
| 来源冲突 | 同期两份文档不同值 | 人工审核 |
| 版本/范围差异 | r0p0 与 r1p1 | 分开，不判矛盾 |
| 抽取错误 | 0x1C 抽成 0x10 | 人工标记 retracted |

### 5.2 版本更新：自动

硬条件：

1. 同一 `document_family_id`
2. 新 revision 更大，或明确 `supersedes`
3. 同一 `subject + predicate + scope`
4. 值不同
5. 没有人工“保留双方”的裁决

动作：

- 新 claim → `active`
- 旧 claim → `superseded`
- 建 `supersedes`
- 自动冲突记录 `version_update / auto_resolved`
- 审计、可撤销

**解决环节：压缩 / canonicalization，不是定期扫描。**

### 5.3 来源冲突：人工

适用：

- 不同来源
- 同来源但 revision 不明
- 同版本不同值
- 范围不同
- 抽取疑似错误
- 同一文档前后矛盾

动作：

- 双方保留，标 `disputed`
- 进审核队列
- 不自动选一个

**发现环节：定期扫描 + 使用中标记。**

### 5.4 人工裁定

允许动作：

- Accept A / Accept B
- Keep both
- Merge
- Split by revision/scope
- Mark extraction error
- Needs more evidence
- Reopen auto supersede

裁定是**写库操作**：

- 更新 claim status
- 写 evidence
- 写冲突决议
- 写审计
- 失效缓存
- 标记 Wiki stale
- 后台重建

权限：

- `wiki-study` / `wiki-work`：只能 flag，不能裁定
- `wiki-manage` / `wiki-admin`：可以裁定

### 5.5 回写节奏

| 类型 | 节奏 |
|---|---|
| 确定性变更（版本、状态、裁定） | 事件驱动，立即 |
| 发现型工作（冲突、近重复、覆盖） | 定期扫描，批量候选 |
| 语义变更（接受/驳回/新 claim） | 人工审核后写库 |

> **确定性的立即回写；发现型的定期扫描；语义型的必须人工。**

---

## 6. LLM-Wiki 方法论

### 6.1 定位

LLM-Wiki 是 **Claim/Evidence 的物化叙事视图**：

```text
ClaimDB / Evidence   = 基表
Graph / Timeline     = 索引/投影
LLM-Wiki             = 物化叙事视图
```

它可以重建、可以过期、可以换 prompt；不能成为事实源。

### 6.2 什么时候建立

- 首次：语料、claim、taxonomy、prompt 基本稳定后
- 增量：新文档/新 claim 影响到的 topic
- 全量：prompt/结构/冲突/版本/模型变化
- 按需：用户打开空页面时后台建
- 定期：stale 页面批量重建

不建议全库 4,000 topics 一次全建。

### 6.3 页面状态

```text
topic
prompt_version
model
claim_ids[]
claim_set_hash
status_counts: active / superseded / disputed
built_at
stale_at
last_used_at
```

更新规则：

| 条件 | 动作 |
|---|---|
| claim_set_hash 没变 | skip |
| 小增量、prompt 没变 | incremental |
| prompt/结构变化 | full rebuild |
| supersede/retract/裁定 | full rebuild |
| disputed 新增 | full rebuild，显示冲突 |
| 高频且过期 | 优先重建 |
| 长期不用 | 降级 |

### 6.4 增量 vs 全量

- 增量：同 prompt 版本、结构不变、只追加
- 全量：prompt/结构/冲突/版本变化
- 增量必须保留旧结构与引用

### 6.5 过期（stale）

- UI 显示 stale
- 问答不把 stale wiki 当权威
- 后台重建
- 重建前回退到 claim/evidence

### 6.6 反哺主库

**不允许 Wiki 文本直接写回 ClaimDB。**

允许的反哺：

| Wiki 发现 | 动作 |
|---|---|
| 无引用/证据不足 | coverage gap → 补文档 |
| 页面冲突 | conflict candidate → 审核 |
| 缺 topic | taxonomy / 建页队列 |
| 同义 topic | alias / merge 建议 |
| 高频页面 | 重建优先级 |
| 用户批注 | review task |
| 新事实 | claim candidate + evidence → 审核 |

> **Wiki 反哺缺口、冲突、优先级、分类，不反哺事实。**

### 6.7 自我进化

不是模型权重学习，而是知识工件持续演化：

```text
事实层：新 claim / supersede / 冲突裁定
程序层：prompt / 结构 / taxonomy / alias / ignore
裁决层：人工决定持久化
导航层：使用频率 / 覆盖 / stale
```

闭环：

```text
Document → Claim → Evidence → Wiki → 使用
   ↑                                  ↓
   └── 补文档 / 改 prompt / 裁定 / 调 taxonomy
```

限制：

- 不用 Wiki 文本训练/回写事实
- 不自动把“看似合理”升级为 claim
- 不无审核覆盖冲突
- 不删除历史

> **自我进化 = 受控的知识工件进化，不是模型自我训练。**

### 6.8 规模策略

LLM-Wiki 不适合全库覆盖。超大知识库里主打：

- 策展入口
- 跨文档叙事
- 术语/结构一致性
- 冲突/版本热点
- Agent 导航层

分层：

```text
Tier 1  100–300 个策展页      自动维护
Tier 2  按需生成/缓存          不自动全建
Tier 3  原始 claims/chunks     只检索
```

控制：

- 只自动重建 curated topics
- 单页 claim 上限（当前 250）
- 子页拆分
- 按 usage/coverage 排优先级
- stale 后台重建
- 低价值 topic 不建页

### 6.9 有它 vs 没它

| 维度 | 无 Wiki | 有 Wiki |
|---|---|---|
| 事实准确性 | 依赖当次检索 | 依赖 claim + 校验 |
| 一致性 | 每次可能不同 | 结构稳定 |
| 速度 | 每次合成 | 读缓存页面 |
| 跨文档叙事 | 弱 | 强 |
| 冲突处理 | 临时 | 显式 |
| 维护成本 | 低 | 中/高 |
| 适合 | 临时问答 | 教学/报告/Agent 入口 |

> **ClaimDB/RAG 是搜索引擎；LLM-Wiki 是门户首页 + 精选条目。**

---

## 7. 层间工作流

```text
Document
  → exact dedup / version
  → Chunk (retrieval)
  → ClaimCandidate
  → CanonicalClaim + Evidence
       ├─ Graph projection
       ├─ Timeline projection
       └─ Wiki page
  → 检索 / 问答 / Wiki / Agent
  → 反馈（缺口/冲突/覆盖/使用）
  → 审核 / 补文档 / 调 prompt / 调 taxonomy
  → 重建
```

事件驱动 vs 定期 vs 人工：

| 工作 | 方式 |
|---|---|
| exact dedup | 入库事件 |
| version supersede | 压缩事件 |
| claim 状态变化 → wiki stale | 事件 |
| 冲突扫描 | 定期 |
| 近重复检测 | 定期 |
| 覆盖缺口 | 定期 |
| 人工裁定 | 使用中/审核，立即写库 |
| Wiki 重建 | stale 队列 + 定期批处理 |

---

## 8. 反模式（禁止）

1. Wiki 文本直接写回 ClaimDB 当事实
2. 用 LLM 输出训练/自我强化
3. 冲突静默选一个
4. 删除旧 claim / 旧版本
5. Graph 直接独立写主图，绕过 claim
6. 去重时把矛盾合并掉
7. 自动把“高置信度”当“已裁决”
8. 让 stale Wiki 参与权威回答
9. 用 URL 相同就无脑跳过内容更新

---

## 9. 当前实现差距

| 能力 | 当前 |
|---|---|
| 完全重复文档/URL | ✅ |
| 单文档 claim/relationship/event 去重 | ✅ |
| 跨文档 canonical claim | ❌ |
| ClaimEvidence | ❌ |
| claim status / version | ❌ |
| 版本 supersede | ❌ |
| 冲突检测/审核 | ❌ |
| 人工裁定写库 | ❌ |
| Graph 挂 claim/evidence | ❌ |
| Wiki 状态/stale/自动重建 | 部分（手动） |
| Wiki prompt intervention | ✅ |
| 三级 taxonomy / alias 合并 | ✅ |
| 大库 tiering | 部分（12 页/29 topics） |

当前基线：

```text
73 docs / 39,870 chunks / 10,573 claims
353 duplicate claim-text groups / 1,491 extra claims
55 duplicate chunk-text groups / 62 extra chunks
12 curated wiki pages
claim coverage 15.94%（effective 17.80%）
```

---

## 10. 决策记录

| ID | 决策 |
|---|---|
| D1 | Claim 是事实源；Graph/Timeline/Wiki 是投影 |
| D2 | 原始文档不可变；干预落在 claim/evidence/status |
| D3 | 输入层只做完全重复 + 版本识别 |
| D4 | 版本更新在压缩层自动 supersede |
| D5 | 来源冲突定期扫描 + 人工审核 |
| D6 | Wiki 不反哺事实，只反哺缺口/冲突/优先级/分类 |
| D7 | Wiki 可重建、可过期、可版本化 |
| D8 | 大库 Wiki 做 Tier 1 策展 + Tier 2 按需，不做全量 |
| D9 | 人工裁定是写库操作，必须审计、可回滚 |
| D10 | 自动决策可被人覆盖；人裁决不被自动静默覆盖 |

---

## 11. 开放问题

1. `document_family_id` 如何自动识别（URL / source+title / PDF metadata）？
2. PDF revision 如何稳定提取？
3. Claim canonical key 是否需要 LLM 结构化 subject/predicate/object？
4. 冲突检测用规则、NLI 还是 LLM judge？成本/误报如何控制？
5. Graph 投影与 LightRAG 索引如何共存？
6. 人工裁定 UI 放在 WebUI 哪个面板？
7. 大规模重建的队列/限流/优先级怎么定？
8. 页面 stale 时答案回退策略如何量化？
