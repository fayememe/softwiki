# 模型与推理服务要求（运营方）

> 版本：2026-11-01  
> 适用：SoftWiki / SWAgent / Hermes 的模型与 embedding 供给  
> 目标：单校/团队试用，100–150 篇文档，10 人以内并发。

---

## 1. 结论先行

运营方需要提供两类 OpenAI-compatible 服务：

```text
1. Chat / LLM       /v1/chat/completions
2. Embedding        /v1/embeddings
```

最低可用组合：

```text
Chat：
  - 快模型：抽取 / NLI / 日常分析
  - 强模型：Wiki / 复杂回答
  - 必须支持 JSON 输出
  - Agent 用模型还必须支持 tool calling

Embedding：
  - OpenAI-compatible
  - 固定维度（当前 1536）
  - 可批量
  - 157 必须能出站访问
```

如果只给 Chat、不给 Embedding：

```text
SoftWiki 可以跑，但只能 BM25 检索；
向量检索/语义召回关闭；
新 KB 的 /api/index 不会生成 vector index。
```

---

## 2. 网络要求

### 2.1 出站

服务器需要 HTTPS 出站到模型网关：

```text
443/tcp
```

允许：

```text
api.deepseek.com            当前 157 可达
<company-llm-gateway>       推荐
<embedding-gateway>         必须
```

157 当前不可达：

```text
api.openai.com
generativelanguage.googleapis.com
```

### 2.2 入站

模型服务不需要对公网开放入站。  
SoftWiki 只作为客户端访问模型网关。

### 2.3 代理

如果模型网关在公司代理后，需要支持：

```text
HTTPS_PROXY
HTTP_PROXY
NO_PROXY
```

并在 `.env` 中配置；不要把代理密码写进 git。

---

## 3. Chat / LLM 要求

### 3.1 协议

必须兼容：

```http
POST /v1/chat/completions
Authorization: Bearer <KEY>
Content-Type: application/json
```

请求字段至少支持：

```json
{
  "model": "...",
  "messages": [{"role":"user","content":"..."}],
  "temperature": 0.1,
  "max_tokens": 4096
}
```

响应至少包含：

```json
{
  "choices": [{"message": {"role":"assistant","content":"..."}}]
}
```

### 3.2 能力

| 能力 | 要求 | 用途 |
|---|---|---|
| 多语言 | 中/英 | 文档与问答 |
| 长上下文 | ≥32k，推荐 64k–128k | 文档窗口/回答 |
| JSON 输出 | 必须稳定 | claim/结构化抽取 |
| Tool calling | Agent 模型必须 | SWAgent / Hermes |
| 指令遵循 | 强 | 引用、拒答、格式 |
| 低温度 | 支持 0–0.3 | 抽取/NLI |
| 流式 | 推荐 | SSE/Agent UX |

### 3.3 两类模型

建议运营方提供两个 model name：

```text
FAST_MODEL     抽取、NLI、日常分析
QUALITY_MODEL  Wiki、复杂回答、报告
```

当前默认：

```text
FAST_MODEL    = deepseek-v4-flash
QUALITY_MODEL = deepseek-v4-pro
```

可以使用等价模型，但必须通过验收测试。

### 3.4 超时与重试

```text
单次 chat 请求超时：120s
Agent 工具调用超时：600s
重试：1–2 次，指数退避
```

`softwiki_ask` 在 BM25-only 模式下可能 1–3 分钟，超时不能低于 300s。

### 3.5 限流

试用期最低建议：

```text
RPM ≥ 60
TPM ≥ 1,000,000
并发 ≥ 8
```

如果低于这个值，需要提前说明，SoftWiki 会降并发/排队。

---

## 4. Embedding 要求

### 4.1 协议

必须兼容：

```http
POST /v1/embeddings
Authorization: Bearer <KEY>
Content-Type: application/json
```

请求：

```json
{"model":"text-embedding-3-small","input":["text 1","text 2"]}
```

响应：

```json
{"data":[{"embedding":[0.1,0.2,...]},{"embedding":[...]}]}
```

### 4.2 维度

当前 vector index 使用 **1536 维**。

要求：

```text
维度必须固定为 1536
```

如果运营方只能提供其他维度：

- 必须全量重建 vector index
- 不能混用旧 index
- 需要先备份

### 4.3 输入与批量

```text
单条最大输入：≥8192 tokens
批量：≥64 条/请求
单请求超时：20s
```

### 4.4 限流

```text
TPM ≥ 1,000,000
并发 ≥ 4
```

当前 SoftWiki 支持：

```text
EMBEDDING_BATCH_SIZE
EMBEDDING_CONCURRENCY
EMBEDDING_TPM
```

### 4.5 没有 Embedding 时

SoftWiki 会：

```text
RAG_ALLOW_BM25_FALLBACK=1
/api/index -> vector_index=false, bm25_index=true
search/ask -> BM25 only
```

这可以作为降级，但不是完整试用体验。

---

## 5. 模型行为要求

### 5.1 抽取

必须能稳定输出 JSON，例如：

```json
{
  "claims": [
    {
      "text": "...",
      "actor": "...",
      "topic": "...",
      "stance": "supportive|cautious|opposed|neutral|unclear",
      "confidence": 0.0
    }
  ]
}
```

要求：

- 不编造文档中不存在的 claim
- 不把目录/页眉/法务模板当 claim
- JSON 可解析率 ≥ 99%

### 5.2 引用

回答/Wiki 必须能遵守：

```text
每个事实句带 [n]
[n] 对应 source/page
无证据时明确说不知道
```

### 5.3 Agent

SWAgent/Hermes 用模型必须支持：

```text
tool calling
多轮工具调用
JSON arguments
```

否则只能 Quick 问答，不能 Agent。

---

## 6. 安全与合规

运营方需确认：

- [ ] 模型不训练客户数据
- [ ] 请求/响应保留策略（建议 0–30 天）
- [ ] 数据存储区域
- [ ] 传输 TLS
- [ ] API key 可按环境/用途分离
- [ ] 支持 key 轮换
- [ ] 支持 IP allowlist 或网关鉴权
- [ ] 不把 prompt/响应写进普通日志
- [ ] 不把 key 写进镜像/仓库

### Key 规则

```text
必须提供 157 专用 key
禁止使用个人 DeepSeek/OpenAI key
禁止多个环境共用同一个 key
```

Key 通过安全渠道交付，放 `.env`，权限 600。

---

## 7. 容量与预算

100–150 篇技术文档的粗略量：

```text
抽取：每篇 6 个窗口 × 3 类抽取
  ≈ 600–900 次 chat 调用

Wiki：12–30 页
  ≈ 30–100 次高质量调用

NLI/冲突：10–50 对
  ≈ 10–50 次判断

问答：10 人以内
  ≈ 每天 100–500 次
```

建议试用配额：

```text
Chat 输入：20M–50M tokens/月
Chat 输出：2M–5M tokens/月
Embedding：20M–50M tokens/月
```

实际取决于文档长度、Wiki 页数和 Agent 使用频率。

---

## 8. 验收测试

运营方交付前必须通过：

### 8.1 Chat

```bash
curl -s "$CHAT_BASE/models" \
  -H "Authorization: Bearer $CHAT_KEY"

curl -s "$CHAT_BASE/chat/completions" \
  -H "Authorization: Bearer $CHAT_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"'$FAST_MODEL'","messages":[{"role":"user","content":"Return JSON: {\"ok\":true}"}],"temperature":0}'
```

要求：

- HTTP 200
- 返回可解析 JSON
- 延迟可接受

### 8.2 Tool calling

用 FAST/QUALITY 中给 Agent 的模型发一个 tool call 请求，确认返回 `tool_calls`。

### 8.3 Embedding

```bash
curl -s "$EMBED_BASE/embeddings" \
  -H "Authorization: Bearer $EMBED_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"'$EMBED_MODEL'","input":["hello"]}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d["data"][0]["embedding"]))'
```

要求：

```text
1536
```

### 8.4 SoftWiki 端到端

```text
[ ] /api/health 200
[ ] ingest 1 篇
[ ] /api/index vector_index=true
[ ] search 有结果
[ ] ask 有页码引用
[ ] wiki build 成功
[ ] Hermes mcp test softwiki 16 tools
```

---

## 9. 交付清单

运营方需要提供：

```text
[ ] Chat base URL
[ ] Chat API key（157 专用）
[ ] FAST_MODEL
[ ] QUALITY_MODEL
[ ] Embedding base URL
[ ] Embedding API key（157 专用）
[ ] Embedding model
[ ] Embedding 维度
[ ] RPM / TPM / 并发
[ ] 超时/重试策略
[ ] 数据保留/训练政策
[ ] 网络白名单/代理
[ ] 联系人/升级路径
```

---

## 10. 当前 157 状态

```text
Chat:      DeepSeek 可访问，但 key 已移除
Embedding: 不可达
检索:      BM25 fallback
Hermes:    WebUI 运行，无模型 key
SWAgent:   停用，等 key
```

需要运营方补齐：

```text
1. 157 专用 Chat key
2. 可达的 Embedding 服务（1536 维）
3. 或明确接受 BM25-only
```
