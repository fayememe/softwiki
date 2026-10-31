# Deployment — 117.133.38.157（team trial）

> 2026-11-01
> 目标：只部署 SoftWiki；**不部署 `armkb`**。新知识库后续单独建。

## 入口

```text
Web:   http://117.133.38.157:6108
MCP:   http://117.133.38.157:6100/mcp
SWA:   http://117.133.38.157:6111
API:   http://127.0.0.1:6200  （仅本机）
```

API 已绑定 `127.0.0.1:6200`，不公网暴露。

## 机器 / 路径

```text
用户：faye
代码：/opt/aitools/apps/softwiki
workspace：/opt/aitools/apps/softwiki/workspace/team
数据库：softwiki_team
Docker：28.5.2
Compose：/usr/local/bin/docker-compose v5.6.1
```

## 当前状态

```text
documents:      0
chunks:         0
claims:         0
entities:       0
relationships:  0
events:         0
```

- `armkb` workspace 已从本机移除
- `softwiki_armkb` 数据库已删除
- 保留 `team` 空 workspace + 配置（topics / permissions / model_profiles / scope）

## SWAgent

- systemd：`swagent.service`
- 容器：`softwiki-api:latest`
- engine：`/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode`
- workspace：`/data/workspace/team`
- 模型：`deepseek-v4-flash`
- 角色：`wiki-research`（只读）

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
- **必须用云安全组/防火墙限制 6108/6100/6111**
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
sudo journalctl -u swagent -f
```

## 注意

- 目标机没有 CI timer；更新代码需要手动同步 + rebuild。
- `armkb` 仍在 javis；本机不再有 `armkb`。
- `team` 是空占位 workspace；新知识库建好后可切换/迁移。
