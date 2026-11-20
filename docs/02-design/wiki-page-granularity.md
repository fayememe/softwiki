# LLM-Wiki 页面粒度：一实体一页

> 状态：🚧 讨论中（2026-11-20 起）
> 相关：[knowledge-system-philosophy.md](./knowledge-system-philosophy.md)、[wiki-prompt-studio.md](../04-guides/wiki-prompt-studio.md)

---

## 1. 问题

当前 LLM-Wiki 的产出单元是 **topic**（`topics.yaml` 里的一条），一个 topic 产出一篇 `<topic>.md`。

trial-host 两个知识库各只配了 1 个 topic，别名写得极宽：

```yaml
coffee:
  aliases: ["coffee-*", "espresso-*", "arabica-*", "robusta-*", "caffeine-*", ...]
```

结果：**6,678 条 claim 压进一篇 28KB 的文章**。

### 1.1 静默截断（比粒度更严重）

`page_generator.py:81`：

```python
max_claims = int(os.getenv("WIKI_MAX_CLAIMS", "250"))
if len(claims) > max_claims:
    claims = sorted(claims, key=lambda c: ((c.confidence or 0), c.published_at or datetime.min),
                    reverse=True)[:max_claims]
```

实测数据：

| 知识库 | canonical claims | 实际送入 LLM | 比例 |
|---|---|---|---|
| coffee | 6,678 | 250 | 3.7% |
| ai-history | 9,514 | 250 | 2.6% |

**`/api/wiki/coverage` 报 99.88% 是假数字**——那是"别名匹配到多少 claim"，不是"页面用了多少"。

---

## 2. 实测：阈值在哪

试点（`deepseek-v4.1-flash`，与线上同配置，只改每页 claim 数）：

| subject | 库内 claim | 发送 | 输出字数 | finish | 判断 |
|---|---|---|---|---|---|
| Cortado | 10 | 10 | 2,415 | stop | ✅ |
| Cold brew | 11 | 11 | 3,383 | stop | ✅ |
| AeroPress | 12 | 12 | 2,427 | stop | ✅ |
| Moka pot | 15 | 15 | 3,631 | stop | ✅ |
| Iced coffee | 23 | 23 | 4,473 | stop | ✅ |
| Coffeehouse | 129 | 129 | 20,559 | stop | ⚠️ 退化 |

### 2.1 小页的优势（AeroPress，12 条）

1. **判别 tangential claim**：12 条里 5 条是磨豆机评测顺带提到 AeroPress，模型自己分到 `## Mentions`。
2. **冲突显式化**（Cold brew，11 条）：把"冷萃酸度低"与"冷萃剥夺风味"、"不常见"与"商业罐装桶装"摆出来，不选边。
3. **引用可追**：`Sources` 段能落到文档名（标题清洗后可达页码）。

### 2.2 大页的退化（Coffeehouse，129 条）

不是崩在长度，是**判别力消失**：

- 9 处"第一间咖啡馆"（Damascus / Mecca / Istanbul 1554 / 1555 / Belgrade 1521 / Livorno 1632 / Venice 1640 / London 1652 / Oxford 1650）——**互相矛盾的记载全部平铺，没有进 Conflicts**；
- 同一事实写两遍（`3,000 coffeehouses [44]` 与 `[61][92]`）；
- `Sources` 退化成区间打包 `[1]–[15], [22]–[31], ...`；
- 日期全丢（`no date given`）。

**阈值区间：50–80 条之间滑坡**（23 条仍清楚，129 条已不行）。

---

## 3. 决策

### D1 — 阈值固定，拆页动态

**一页上限固定 25 条**，不做动态。

理由：阈值取决于模型上下文、`max_tokens`、token 预算，都是部署选择而非内容属性。动态会让同一 subject 的页面随基础设施漂移，无法版本比对、无法解释"为什么这页少了半截"。

配置：

```yaml
wiki:
  page_claim_limit: 25          # 固定；超过则拆页，绝不静默截断
  oversize_strategy: split      # split | fail
```

不提供 `auto` / `dynamic` 选项。

### D2 — 上限不是填充量

```
subject 12 条  → 一页 12 条
subject 23 条  → 一页 23 条
subject 60 条  → 拆成 3 页，不压进一页
subject 500 条 → 这是 topic，不是 subject
```

95% 的 subject 低于 25 条，直接一页。

### D3 — 超限按二级维度拆，不按序号切

| subject 类型 | 拆分依据 |
|---|---|
| 实体（产地/公司/产品） | `relationships` 的关系类型分组 |
| 概念（工艺/品类） | 子主题聚类 |
| 仍超限 | 按时间或文档来源切，页首标注 |

父页永远存在 = 摘要 + 子页清单，导航结构稳定。

### D4 — 禁止静默截断

超过上限时：**要么拆页成功，要么生成失败并报错**。绝不取前 25 条写出看起来完整的页面。

每页记录 `claims_covered / claims_total`，UI 显示 `23/23` 或 `25/60 → 见子页`。

### D5 — 产出单元 = subject

subject 来源优先级：

1. `canonical_claims.subject`（结构化字段；当前 coffee 大面积为 null）
2. 回退到 `entities` + `relationships` 的实体名匹配（**当前可用**）

`topics.yaml` 降级为**策展覆盖层**：决定导航顺序、导语、别名归并，不再决定"全库只有一页"。

### D6 — 规模估算（coffee 实测）

实体连接度分布：

| 关系数 | 实体数 | 占比 |
|---|---|---|
| 0（孤立） | 465 | 7.7% |
| 1–2 | 4,219 | **70.3%** |
| 3–5 | 825 | 13.7% |
| 6–10 | 285 | 4.7% |
| 11–30 | 165 | 2.7% |
| 31+ | 46 | 0.8% |

70% 的实体只出现 1–2 次 = 抽取噪声，不该建页。

候选门槛：

- 关系数 ≥ 3 → 1,336
- 关系数 ≥ 5 → 652
- 关系数 ≥ 6 → 496
- 关系数 ≥ 11 → 211

**结论：coffee 约 400–600 页**（不含 category 聚合页与索引页）。

---

## 4. 输出布局

```
workspace/<kb>/exports/wiki/
├── topics/          # 旧的 topic 大页（保留兼容）
│   └── coffee.md
└── pages/           # 新：一 subject 一页
    ├── index.json   # 目录：subject / type / claims_covered / claims_total / slug
    ├── aeropress.md
    ├── cortado.md
    └── ...
```

每个 `.md` 头部注释记录：`subject / claims_total / claims_covered / model / finish / generated_at`。

---

## 5. 实现状态（2026-11-20）

已完成：

- `softwiki/wiki/subject_pages.py`
  - `subject_candidates()`：按关系度排序实体，过滤稀疏实体（默认 ≥5 条关系）
  - `_is_library_theme()`：排除覆盖全库共享 ≥15% 的"实体"（如 coffee 库里 `Coffee` 一词命中 3,464/6,686 条），否则会退化成 140 个重述语料的分页
  - `generate_subject_pages()`：一实体一页；超限按 `SUBJECT_PAGE_CLAIM_LIMIT` 拆分；`oversize="fail"` 时直接报错而非截断
  - 每页头部注释记录 `claims_covered / claims_total / model / finish / generated_at`
  - `_slugify()` 做 Unicode 折叠（`Nestlé` → `nestle`）
- API：`GET /api/wiki/pages`、`POST /api/wiki/pages/build`、`GET /api/wiki/pages/{slug}`
- WebUI：`WikiPagesPanel`（侧栏 **Wiki Pages**），搜索 + 类型筛选 + 分页 tab + `25/144 claims` 显式提示
- 批量脚本：`scripts/wiki_build_batch.py`
- 测试：`tests/test_wiki_subject_pages.py`（9 项）

实测（trial-host，2026-11-20）：

| 库 | 候选 subject | 说明 |
|---|---|---|
| coffee | 537 | 排除 `Coffee` 母题后 |
| ai-history | 762 | |

拆页验证（Nestlé，39 条）：`nestle-p1` 25 条 + `nestle-p2` 14 条 = 39，**一条不丢**。

UI 冒烟：`25/144 claims` 徽章、`Split into 6 parts` tab、正文引用 `[n]`、`Sources` 段均正常，无 pageerror。

## 6. 待办

- [x] `softwiki/wiki/subject_pages.py`
- [x] 阈值配置与拆页逻辑（D1/D3）
- [x] 禁止静默截断（D4）
- [x] `/api/wiki/pages` + `/api/wiki/pages/{slug}`
- [x] WebUI 浏览界面
- [x] trial-host 两库批量生成
- [x] 侧栏分组重构；`wiki` 面板下线，`wikipages` 更名 **LLM Wiki**
- [x] documents / claims / LLM Wiki 列表分页（服务端 `limit/offset`）
- [x] 徽章完整数字；表格列宽与行距优化
- [x] `AdminPanel`：用户列表（角色 / pending / kb_scope）+ 审计日志
- [ ] 摘要段不复述事实（prompt 已在 SYSTEM_PROMPT 中修正，待抽查效果）
- [ ] 文档标题清洗（`Document` / `Study authors`）
- [ ] `topics.yaml` 作为策展覆盖层接入（当前未参与）
- [ ] 增量重建：claim 变更时只重生成受影响 subject
- [ ] 与 `wikiweb` 门户对接（门户由 agent 生成，另行讨论）
- [ ] Home 跨 KB 总览（统计 + 日志）
- [ ] KB 管理面板（注册表 / 卸载脱钩）

---

## 决策记录

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-11-20 | 一页上限固定 25 条，超限拆页 | 试点实测 23 条清楚、129 条退化；阈值随基础设施漂移会让页面不可比对 |
| 2026-11-20 | 禁止静默截断 | 当前 250 条上限导致 99.88% 覆盖率是假数字，页面缺 96% 内容而不自知 |
| 2026-11-20 | `topics.yaml` 降级为策展覆盖层 | 粒度应由内容（subject）决定，而非手工配置 |
| 2026-11-20 | wikiweb 与 LLM-Wiki 是两条独立管线 | wikiweb 由外部生成器产出静态 HTML；LLM-Wiki 是 `page_generator` 的产物 |
| 2026-11-20 | 母题实体（覆盖 ≥15% 语料）不建页 | coffee 库中 `Coffee` 命中 3,464/6,686 条，建页会拆成 140 个重述语料的分页，等于换皮的大文 |
| 2026-11-20 | subject 至少 5 条 claim 才建页 | 1 条 claim 的实体产出单句页面（如 `Starbucks Corporation` 与 `Starbucks` 重复），只有导航噪声 |

---

## 7. 界面（2026-11-20）

侧栏按职责分组，`wiki` 面板下线，原 `wikipages` 更名为 **LLM Wiki**（沿用原 wiki 图标）：

```
faye · admin          ← 用户 + 工作模式（admin/work/...）
Current KB            ← 知识库选择

Home
─── KNOWLEDGE ───
Documents / Claims / Graph / Timeline / LLM Wiki
─── ASSIST ───
Chat
─── CONTRIBUTOR ───   （work 及以上可见）
Ingest / Conflicts
─── ADMIN ───         （admin 可见）
New KB / Users
Wiki Portal ↗
```

界面规范：

- **名单分页**：documents / claims / LLM Wiki 一律分页（默认 50/页），服务端 `limit/offset`，不再整表下发（claims 6,691 条曾经全量渲染）。
- **徽章**：`6,691` 显示完整数字，超过 9999 才截断为 `9999+`。
- **表格排版**：短值列固定宽度（actor 120px、stance 90px、date 96px），长文本列吃剩余宽度；行内 padding 从 14px 降到 9px；文档标题与链接同排，链接用 `↗` 图标代替文字。
