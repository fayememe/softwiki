# 准商用 Demo 计划（ARM 技术文档库）

> 状态：🚧 试用/售前 demo（2026-10-31）
> 环境：`http://build.example.internal:6108`；API `:6200`；Agent `:6111`
> 目标：15–30 分钟讲清“可追溯的技术知识系统”，不是通用聊天机器人。

---

## 1. Demo 目标

让客户在 15 分钟内看到四件事：

1. **答案有出处**：页码、source、原文片段。
2. **事实可裁决**：claim / evidence / disputed / 人工裁定。
3. **知识可投影**：Wiki、Graph、Timeline 都来自同一事实层。
4. **研究可外包**：SWAgent 能多步检索，但只读、有工具轨迹。

一句话话术：

> “我们不是让模型记住文档，而是把文档变成可追溯、可裁决、可投影的 Claim。”

---

## 2. Demo 前检查（5 分钟）

**先把左侧角色切到 `Admin · all` 或 `Manage · ingest`。** 默认是 `wiki-study`，只读。



```bash
# API / Web
curl -s http://127.0.0.1:6200/api/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:6108/

# 知识状态
curl -s http://127.0.0.1:6200/api/knowledge/metrics | python3 -m json.tool

# Agent
curl -s http://127.0.0.1:6200/api/agent/status

# 当前冲突队列（应至少有 1 条 NLI 冲突，或按演示需要重置）
curl -s 'http://127.0.0.1:6200/api/conflicts?status=open'
```

最低可用状态：

```text
canonical_claims > 9,000
stale_wiki_artifacts = 0
wiki pages = 12
open conflicts >= 1（演示冲突面板时）
Agent status = available
```

如果 SWAgent 离线：

```bash
sudo systemctl restart softwiki-agent-web
journalctl -u softwiki-agent-web -n 100 --no-pager
```

---

## 3. 15 分钟主 Demo

### 0:00–1:30 开场

打开 Web，左侧工作区 `kb-alpha`。

话术：

> “这是一套自部署的技术知识系统。语料是 ARM IP 文档：73 篇、约 4 万 chunks、9,766 条 canonical claims。今天重点不是聊天，而是看它怎么保证‘答案有依据、冲突可审核’。”

### 1:30–5:00 Quick 问答

问题：

```text
What registers does the PL031 RTC provide?
```

看点：

- 答案列出 RTCDR / RTCMR / RTCLR / RTCCR / RTCIMSC / RTCRIS / RTCMIS / RTCICR
- 引用带页码（如 p. 23）
- 右侧 source 显示文档、页码、原文片段

话术：

> “每个结论都能回到原文页码。不是模型‘记得’，是检索 + claim + citation。”

### 5:00–8:00 Claim / Evidence / 冲突

打开 **Claims**，说明：

- raw claims 是抽取证据
- canonical claims 是去重后的查询单元
- evidence 保留文档、页码、引用
- disputed 不会静默选边

打开 **Conflicts**：

- 展示 NLI 抓到的 DATA1 / DATA2 位重叠冲突
- 说明：版本更新可自动 supersede；来源冲突要人工审核
- 展示 accept A/B、keep both、mark error、needs evidence
- 强调：审核会写 claim status + audit + Wiki stale

话术：

> “冲突不是让模型自己猜。规则/版本冲突自动处理，来源冲突进人工队列。”

### 8:00–11:00 Wiki

打开 **Wiki**：

- AMBA / PL031 技术页
- 页面结构：Summary / Block Overview / Register Map / Interfaces / Disputed Facts
- 点击 **History** 展示旧版本
- 说明 stale banner + 自动 rebuild worker

话术：

> “Wiki 不是事实源，是 Claim 的叙事投影。claim 变了，页面会 stale；worker 自动重建，历史版本保留。”

### 11:00–13:00 Graph / Timeline

打开 **Graph**：

- NIC-400 / AMBA 关系
- 只展示 active

打开 **Timeline**：

- PL031 / ARM 文档事件
- 事件挂 canonical claim

话术：

> “Graph 和 Timeline 不是第二套真相，是 Claim 的投影；claim disputed/superseded，投影跟着变。”

### 13:00–15:00 Agent / 收尾

打开 **Agent**：

```text
Compare the interrupt behavior of PL031 and NIC-400, with page citations.
```

看点：

- research steps
- `softwiki_ask` / `softwiki_search`
- source 卡片
- 不会调用写工具

收尾话术：

> “Quick 负责快问快答，SWAgent 负责多步研究；两者共用同一个只读知识库。”

---

## 4. 30 分钟加长版

在 15 分钟基础上加：

### Report

- Chat 里点 **Report**，选 `research-report`
- 展示 manifest、source、页码
- 说明可交付给客户/老师

### Prompt Studio

- Wiki → Prompt Studio
- 写一句 intervention，例如：
  - “Always include a register table with offset, reset value, and page.”
- Preview（只写 preview 目录）
- Apply 后重新生成
- 强调：提示词是表现层，不是事实

### 覆盖率与限制

```bash
curl -s http://127.0.0.1:6200/api/wiki/coverage
```

说明：

- claim 覆盖率约 15.94%（1,685/10,573）
- 12 个策展页；Tier 2 按需页未开
- 未策展 topic 仍可走 claim/chunk 检索
- 这是“准商用”，不是“全自动知识员工”

---

## 5. 失败预案

| 问题 | 处理 |
|---|---|
| LLM 慢/超时 | 改用已生成 Wiki 页面 + Claims；说明后台生成 |
| SWAgent 离线 | 用 Quick 模式；或重启 `softwiki-agent-web` |
| 答案不完整 | 换更具体的问题；展示 source 页码，不硬撑 |
| 冲突队列为空 | 用 NLI 脚本生成候选，或只讲机制不现场开 |
| Wiki stale | 点击 Regenerate；worker 会自动跑 |
| 网络/API 失败 | 切到本地预生成页面/截图；不要现场 debug 太久 |

**不要现场做的操作：**

- 不要 `rebuild_index`
- 不要 ingest 大 PDF
- 不要批量 adjudicate
- 不要改 workspace
- 不要展示 `.env` / 密钥

---

## 6. Demo 成功标准

客户离场前应能复述：

```text
1. 答案能回到页码/原文
2. Claim 有 evidence，冲突可人工审核
3. Wiki/Graph/Timeline 是 Claim 投影
4. SWAgent 只读、有工具轨迹
5. 这是自部署、单库、准商用版本
```

---

## 7. 演示后

- 记录客户问题与失败点到 `progress.md` / CRM
- 若客户要求多用户/权限/TLS/OCR：明确列入下一阶段，不现场承诺
- 若客户提供新语料：先建独立 workspace，不污染 `kb-alpha`
