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
coffee-kb:      documents 185 / chunks 3,489 / claims 6,691 / relationships 8,179 / events 2,297
ai-history-kb:  documents 160 / chunks 5,497 / claims 9,526 / relationships 12,067 / events 3,279
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
- 2026-11-02 pilot 因 157 出口封锁只入库 12 篇（4 + 8），已由「本地抓取 + 远侧入库」弥补，见下节。
- 目标机不要直接抓外网 URL 入库（见「出口封锁实测」）。

## 语料构建管线（2026-11-03）

157 的出口限制无法绕过 DNS 修好，改为**在开发机抓正文、以 markdown 推送入库**。

```bash
# 1. 本地抓取（front matter 带 title/author/date/url）
python scripts/trial_fetch.py --kb coffee --out /tmp/trial/coffee \
    --sources wiki,rss,urls,europepmc --target 190
python scripts/trial_fetch.py --kb ai-history --out /tmp/trial/ai-history \
    --sources wiki,urls,rss --target 185

# 2. 打包推到目标机
tar -czf - -C /tmp/trial coffee | ssh faye@117.133.38.157 'tar -xzf - -C /tmp/trial-ingest'

# 3. 节流入库（按 pending/extracting 文档数限流，卡死 8 分钟自动置 failed）
bash /tmp/trial_ingest.sh /tmp/trial-ingest/coffee http://127.0.0.1:6200 \
    softwiki-postgres-1 softwiki_coffee 3

# 4. 建 chunk + 向量 + BM25
curl -s -X POST -H "X-SoftWiki-Role: wiki-manage" http://127.0.0.1:6200/api/index
```

来源目录：`scripts/trial_sources.py`。当前构成：

| KB | Wikipedia | arXiv(ar5iv) | SEP | 行业/媒体 RSS | Europe PMC |
|---|---|---|---|---|---|
| coffee | 115 | — | — | 41 | 34 |
| ai-history | 121 | 17 | 10 | 15 | — |

### 出口封锁实测（2026-11-03）

DNS 与 TCP 是两层独立封锁，**改 DNS 解决不了后者**：

| 目标 | 当前 resolver | 用真实 IP + 正确 SNI 强制访问 |
|---|---|---|
| en.wikipedia.org | `2001::1`（伪造） | 3 个真实 IP 全部黑洞超时 |
| theguardian.com | `face:b00c`（Facebook 段） | `000` / 0.11s（TCP RST） |
| www.newyorker.com | `2001::9f8a:1414`（伪造） | `000` / 0.22s |
| www.theatlantic.com | `face:b00c` | `000` / 0.17s |

- 157 无全局 IPv6，无 `*_PROXY`；AliDNS DoH 返回的也是污染结果，Cloudflare DoH 不可达。
- 可达且已在使用：`en.wikipedia.org`（仅开发机）、ar5iv、SEP、Europe PMC、dailycoffeenews、baristamagazine、coffeegeek、IEEE Spectrum、MIT Tech Review、computerhistory.org。
- 排除：Guardian / NewYorker / Atlantic / BBC / ai.stanford.edu（TCP 封锁）、perfectdailygrind（feed 403）、science.org / smithsonianmag（403，UA 可解但未采用）。

### 已知缺口

- markdown 文档没有页码，`/api/ask` 的 `page_start` 为 `None`；页码引用只在 PDF 上有意义。
- ai-history 的 RSS 稿件里约 20 篇被 `scope_guard` 判为越界（企业治理、预测类新闻），因此 184 篇只入库 160。
