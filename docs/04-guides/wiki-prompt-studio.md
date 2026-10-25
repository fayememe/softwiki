# Wiki Prompt Studio（提示词干预闭环）

> 目标：让用户用**可选、可变粒度**的 prompt 干预 Wiki 生成；先 Preview，满意后再 Apply；保存后持续作用于后续重建。
> 入口：WebUI → Wiki → **Prompt Studio**；或 API。

---

## 1. 设计原则

Prompt 不是固定 profile，而是生成算法 input 的一个**可选干预层**：

```text
base_input = topic + group + claims + events + sources + 默认生成契约
intervention = 可空 / 一句话 / 章节规则 / 完整模板
final_input = compose(base_input, intervention)
page = generate(final_input)
preview(page) → 人看效果 → 调整 intervention → 再 preview
```

- 可空：走默认生成
- 一句话：追加到系统指令
- `[SECTION: 寄存器与编程模型] ...`：页面内规则
- 完整模板：整体替换默认结构
- 保存后：按 global / group / topic 叠加

---

## 2. 使用流程

1. Wiki → 选择 topic
2. 点 **Prompt Studio**
3. 输入 intervention（可空）
4. 指定 topics（最多 3 个；可只测一个）
5. **Preview**：只写 `exports/wiki/preview/<run_id>/`，canonical 不动
6. 看章节、引用数、warnings、模型、耗时
7. 不满意 → 改 prompt → 再 Preview
8. 满意 → **Save global / Save group / Save topic**
9. **Apply to topics**：写 canonical wiki
10. 后续 `Generate/Regenerate` 或自动重建会自动叠加已保存 intervention

---

## 3. 保存与版本

- 存储：`workspace/<ws>/config/wiki_interventions.yaml`
- scope：
  - `global`
  - `group:<group>`（如 `group:IP 产品`）
  - `topic:<topic>`（如 `topic:rtc-register-map`）
- 页面状态 JSON 记录 `intervention_hash`
- intervention 变了 → **full rebuild**
- intervention 没变、只有新 claims → 允许增量
- Preview/Apply 都带 `include_saved`，可只测 ad-hoc

---

## 4. API

```text
GET    /api/wiki/interventions
POST   /api/wiki/interventions
DELETE /api/wiki/interventions/{id}

POST   /api/wiki/preview
POST   /api/wiki/apply

GET    /api/wiki/coverage
```

Preview 请求：

```json
{
  "topics": ["rtc-register-map"],
  "intervention": "所有页面先给结论，再给证据；每个事实必须有 [n]。",
  "include_saved": true
}
```

Apply 请求：

```json
{
  "topics": ["rtc-register-map"],
  "intervention": null,
  "include_saved": true
}
```

---

## 5. Prompt 范例

### 5.1 大原则（global）

```text
所有页面先给结论，再给证据。
每个事实性句子必须有 [n]；没有证据写“证据不足”。
不得编造页码、寄存器地址、信号名或复位值。
不要删除默认章节；没有证据的章节保留标题并写“暂无足够证据”。
```

### 5.2 IP 产品页（group:IP 产品 / topic:cm55）

```text
这是 IP 产品页。重点回答：
1. 产品定位与系统角色
2. 架构与内部组成
3. 外部接口/总线
4. 寄存器与编程模型
5. 低功耗/时钟/复位
6. 调试与追踪
7. 集成要点与限制

保持以下结构：
# {{topic}}
## 1. 产品定位
## 2. 架构与组成
## 3. 接口与总线
## 4. 寄存器与编程模型
## 5. 低功耗与时钟
## 6. 调试与追踪
## 7. 集成要点
## 8. 限制与开放问题
## 9. Sources

寄存器章节用表格：Offset | Name | Access | Width | Reset | Description。
每个表格行尽量带 [n]。
```

### 5.3 协议页（group:协议 / topic:amba-axi）

```text
这是协议页。重点回答：
1. 协议范围
2. 角色、信号、通道
3. 状态机/握手
4. 时序与规则
5. 错误/中止/超时
6. 低功耗/时钟含义
7. 典型实现
8. 常见误区

保持以下结构：
# {{topic}}
## 1. 协议范围
## 2. 角色与信号
## 3. 状态机与握手
## 4. 时序与规则
## 5. 错误与中止
## 6. 低功耗含义
## 7. 典型实现
## 8. 开放问题
## 9. Sources

握手章节用状态表：State | Trigger | Next | Notes。
明确区分“协议规定”与“某实现的选择”。
```

### 5.4 技术页（group:技术 / topic:low-power）

```text
这是技术页。重点回答：
1. 问题定义
2. 核心机制
3. 配置/寄存器/信号
4. 权衡与代价
5. ARM IP 实例（CM55/U55/NIC-400/PL031...）
6. 验证与指标
7. 开放问题

保持以下结构：
# {{topic}}
## 1. 问题定义
## 2. 核心机制
## 3. 配置与控制
## 4. 权衡与代价
## 5. ARM IP 实例
## 6. 验证与指标
## 7. 开放问题
## 8. Sources

第 5 节按 IP 分小节；不要把单个 IP 的实现说成协议规定。
```

### 5.5 页面内规则（section-level）

```text
[SECTION: 寄存器与编程模型]
用表格：Offset | Name | Access | Width | Reset | Description。
没有寄存器证据时写“知识库未提供完整寄存器表”，不要猜。

[SECTION: 低功耗与时钟]
先写电源/时钟域结论，再写 P-Channel/Q-Channel 握手。
```

---

## 6. 当前 claim 覆盖率

```bash
curl http://10.3.9.29:6200/api/wiki/coverage
```

当前（2026-10-25）：

- total claims: **10,573**
- mapped: **360**（3.4%）
- unmapped: **10,213**
- ignored: **0**
- canonical topics: **29**

低覆盖率主要来自大量法务/文档模板 topic（`inclusive-language`、`warranty-disclaimer`、`copyright` 等）。
后续通过 `__ignore__` + aliases + 新 canonical topic 提升。

---

## 7. 已知限制

- Preview 目前是同步生成，30–60s/页；一次最多 3 页。
- Apply 会写 canonical；必须先 Preview。
- 当前没有自动重建接线（auto rebuild）；保存的 intervention 会在手动 Generate/Regenerate 时生效。
- Prompt 不能保证 100% 结构稳定；用 Preview + diagnostics 验收。
- 旧页面首次重建会因 `intervention_hash` 缺失而 full rebuild。
