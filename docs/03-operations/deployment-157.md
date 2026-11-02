# Deployment — 117.133.38.157（team trial）

> 2026-11-01
> 目标：只部署 SoftWiki；**不部署 `armkb`**。新知识库后续单独建。

## 两个知识库

| KB | Web | MCP | API | database |
|---|---|---|---|---|
| `coffee-kb` | 6108 | 6100 | 127.0.0.1:6200 | `softwiki_coffee` |
| `ai-history-kb` | 6109 | 6102 | 127.0.0.1:6202 | `softwiki_ai_history` |

`team` 已删除；`armkb` 未部署。

语料目标：每个 KB **100–200 篇**，按 **150 篇/库**推进；先各 20 篇 pilot。

## 入口

```text
Coffee Web:      http://117.133.38.157:6108
AI History Web:  http://117.133.38.157:6109
Coffee MCP:      http://117.133.38.157:6100/mcp
AI History MCP:  http://117.133.38.157:6102/mcp
Coffee SWA:      http://117.133.38.157:6111
AI History SWA:  http://117.133.38.157:6112
Coffee API:      http://127.0.0.1:6200
AI History API:  http://127.0.0.1:6202
```

API 已绑定 `127.0.0.1:6200`，不公网暴露。

## 机器 / 路径

```text
用户：faye
代码：/opt/aitools/apps/softwiki
workspace：/opt/aitools/apps/softwiki/workspace/{coffee,ai-history}
数据库：softwiki_coffee / softwiki_ai_history
Docker：28.5.2
Compose：/usr/local/bin/docker-compose v5.6.1
```

## 当前状态

```text
coffee-kb:      documents 4 / chunks 34 / claims 76
ai-history-kb:  documents 8 / chunks 67 / claims 146
```

- `team` 已删除
- `armkb` 未部署
- 每个 KB 独立 topics / permissions / model_profiles / scope

## SWAgent

两个独立实例，各自绑定一个 KB：

| KB | systemd | 容器 | 端口 | workspace |
|---|---|---|---|---|
| coffee | `swagent-coffee.service` | `swagent-coffee` | 6111 | `/data/workspace/coffee` |
| ai-history | `swagent-ai.service` | `swagent-ai` | 6112 | `/data/workspace/ai-history` |

- engine：`/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode`
- 模型：`deepseek-v4.1-flash`（oneroute）
- 角色：`wiki-research`（只读）
- AI 实例的 MCP：`http://127.0.0.1:6102/mcp`

WebUI 的 KB selector 现在直接跳转 `6108` / `6109`，不再用旧 workspace 下拉切换。

## Hermes Agent + WebUI

```text
容器：hermes
镜像：nousresearch/hermes-agent:latest
Dashboard：http://117.133.38.157:9119
Gateway：http://127.0.0.1:8642（仅本机）
数据：/opt/aitools/apps/hermes（挂载 /opt/data）
版本：0.22.5
模型：deepseek-v4.1-flash（157 oneroute key 已配置；不使用个人 DeepSeek key）
```

Dashboard 使用 basic auth（用户名 `admin`；密码见目标机
`/opt/aitools/apps/hermes/.env`，不要提交到 git）。

> 2026-11-01 更新：已从 157 移除个人 DeepSeek/OpenAI/embedding key；SoftWiki
> `model_profiles.yaml` 的 `api_key` 已置空。需要 157 专用 key 后再启用 LLM。
> SWAgent 已恢复，但拆成 coffee：6111 / ai-history：6112 两个实例。

MCP：

```yaml
mcp_servers:
  softwiki_coffee:
    url: http://host.docker.internal:6100/mcp
    headers:
      X-SoftWiki-Role: wiki-work
    timeout: 600
  softwiki_ai:
    url: http://host.docker.internal:6102/mcp
    headers:
      X-SoftWiki-Role: wiki-work
    timeout: 600
```

验证：

```bash
sudo docker exec -i hermes hermes mcp test softwiki
# Connected, 16 tools
sudo docker exec -i hermes hermes chat -q "Use SoftWiki to list documents." --oneshot -Q
# 0
```

## 网络限制

该机器无法访问：

- `api.openai.com`
- `generativelanguage.googleapis.com`

可访问：

- `api.deepseek.com`

因此：

- LLM：使用 DeepSeek
- embedding：OpenAI 不可达；RAG 已启用 BM25 fallback
- 当前可查询；没有向量 embedding，检索质量会低一些
- 若需要向量检索/ingest embedding，需要代理或可达的 embedding 服务

## 安全边界

- Web / SWA / MCP 目前监听 `0.0.0.0`
- 没有登录/API key
- 角色 header/cookie 可伪造
- API 已只绑本机
- **必须用云安全组/防火墙限制 6108/6109/6100/6102/6111/6112/9119**
- 对外前需要登录/反代/TLS/API key

## 常用命令

```bash
cd /opt/aitools/apps/softwiki

# 状态
sudo /usr/local/bin/docker-compose --project-name softwiki ps
curl -s http://127.0.0.1:6200/api/status
curl -s http://127.0.0.1:6200/api/swa/status

# 日志
sudo /usr/local/bin/docker-compose --project-name softwiki logs -f api
sudo journalctl -u swagent-coffee -f
sudo journalctl -u swagent-ai -f
```

## 注意

- 目标机没有 CI timer；更新代码需要手动同步 + rebuild。
- `armkb` 仍在 javis；本机不再有 `armkb`。
- `team` 已删除；不要再把 `swagent` 指回 `team`。
- 2026-11-02 pilot 因 157 DNS 污染/路由不可达，Wikipedia/Guardian/NewYorker 等大量 URL 失败；需换可达来源。
