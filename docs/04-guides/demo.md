# Demo 流程（ARM 技术文档库）

> 当前：`armkb` / PostgreSQL / `http://10.3.9.29:6108`

## 1. 基础问答 + 页码引用

问：

```text
What registers does the PL031 RTC provide?
```

期望：

- 答案里列出 RTCDR / RTCMR / RTCLR / RTCCR / RTCIMSC / RTCRIS / RTCMIS / RTCICR
- 引用带页码，例如 `p.5` / `pp.9-10`
- 点开 source 能看到页码和原文片段

## 2. Agent 模式（opencode，深度研究）

Chat 输入框上方有 **Quick / Agent** 切换：

- **Quick**：`AnswerEngine`，快、基于 armkb、页码引用。
- **Agent**：opencode agent，只读 KB + websearch，显示 research steps 和工具调用；通常 20–60s。

也可以直接打开独立的 opencode 页面：`http://10.3.9.29:6111`（WebUI 左侧 **Agent** 或 `Agent ↗` 按钮）。

Agent 健康检查：

```bash
curl http://10.3.9.29:6200/api/agent/status
# available=true, default_agent=wiki-research, model=gemini-compat/gpt-4.1-mini
```

示例问题：

```text
List the main registers of the PL031 RTC and cite the datasheet pages.
```

期望：

- research steps 里出现 `softwiki_ask` / `softwiki_search`
- 答案有 RTCDR..RTCICR，引用页码（如 pp. 9-10 / p. 23）
- 下方 source 卡片可展开
- 不会调用 `softwiki_ingest` / `softwiki_index`（permission deny）

如果 Agent 离线：

```bash
sudo systemctl restart softwiki-agent-web
journalctl -u softwiki-agent-web -n 100 --no-pager
```

注意：当前 PDF 抽取的部分标题是 `Untitled Document`，页码仍有效；标题清洗是后续数据质量问题。

## 3. 学术分析 workflow

在 Chat 的 workflow 下拉框选 `Academic Analysis`，或直接调 API：

```bash
curl -X POST http://10.3.9.29:6200/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Compare the PL031 register model with the AXI handshake model.","workflow":"academic-analysis"}'
```

期望：答案按“拆解 → 来源批判 → 时间线 → 竞争解释 → 局限”的顺序组织；证据不足时明确说明。

## 4. 生成报告

Chat 里点 `Report`，或：

```bash
curl -X POST http://10.3.9.29:6200/api/report \
  -H 'Content-Type: application/json' \
  -d '{"question":"What registers does the PL031 RTC provide?","template":"research-report","workflow":"academic-analysis"}'
```

返回 `report_id` 后下载：

```bash
curl -O http://10.3.9.29:6200/api/report/<report_id>
```

`manifest.json` 在 `/api/report/<report_id>/manifest`。

## 5. 验收脚本

```bash
python scripts/run_acceptance.py --api http://127.0.0.1:6200
```

读取 `tests/acceptance/golden_questions.yaml`，检查关键词、页码引用、拒答。

## 备注

- 权限/登录不在 demo 范围；当前实例按 `wiki-admin` 使用。
- 全量窗口化重抽可能还在跑：`/tmp/armkb-reextract2.log`。
