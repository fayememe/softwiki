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

## 2. 学术分析 workflow

在 Chat 的 workflow 下拉框选 `Academic Analysis`，或直接调 API：

```bash
curl -X POST http://10.3.9.29:6200/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Compare the PL031 register model with the AXI handshake model.","workflow":"academic-analysis"}'
```

期望：答案按“拆解 → 来源批判 → 时间线 → 竞争解释 → 局限”的顺序组织；证据不足时明确说明。

## 3. 生成报告

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

## 4. 验收脚本

```bash
python scripts/run_acceptance.py --api http://127.0.0.1:6200
```

读取 `tests/acceptance/golden_questions.yaml`，检查关键词、页码引用、拒答。

## 备注

- 权限/登录不在 demo 范围；当前实例按 `wiki-admin` 使用。
- 全量窗口化重抽可能还在跑：`/tmp/armkb-reextract2.log`。
