# SoftWiki / SWAgent 交付与运维手册

> 版本：2026-11-01  
> 适用：远端机器（当前 `117.133.38.157`）的 opencode / Hermes 操作者  
> 原则：**按手册执行；不确定先查状态；不要猜命令；不要提交密钥。**

---

## 0. 先读这一页

### 0.1 这套系统是什么

```text
SoftWiki = 文档 → chunk + claim → canonical claim + evidence
         → 冲突/人工裁定 → Answer / Graph / Timeline / Wiki
SWAgent  = SoftWiki 的 Agent 产品（opencode engine）
Hermes   = 外部 Agent + WebUI，用 MCP 调 SoftWiki
```

### 0.2 三个名字不要混

| 名称 | 含义 |
|---|---|
| **SWAgent / SWA** | SoftWiki 的 Agent 产品/UI；工程名 `swagent` |
| **opencode engine** | SWAgent 底层运行时，pinned 1.19.5 |
| **Hermes** | 独立 Agent，带 WebUI；通过 MCP 使用 SoftWiki |
| **personal opencode** | 用户自己平时用的 opencode，和 SWAgent 隔离 |

### 0.3 当前 157 状态

```text
Web:      http://117.133.38.157:6108
API:      http://127.0.0.1:6200        （仅本机）
MCP:      http://117.133.38.157:6100/mcp
SWAgent:  :6111                         （当前停用，等专用 key）
Hermes:   http://117.133.38.157:9119    （dashboard；basic auth）
Gateway:  http://127.0.0.1:8642         （仅本机）
workspace: team
documents: 0
armkb:     未部署
```

### 0.4 操作纪律

1. 先读本手册，再执行。
2. 破坏性操作前先备份：
   - `pg_dump`
   - workspace `tar`
3. 不要打印/提交：
   - `.env`
   - API key
   - Dashboard 密码
   - 数据库密码
4. 不要对公网暴露 `6200 / 6100 / 6111 / 9119`，除非有安全组/VPN/反代。
5. 角色是自报的信任控制，不是安全边界。
6. 一次只做一个逻辑变更；完成后验证。

---

## 1. 机器与目录

### 1.1 157 目录

```text
/opt/aitools/apps/softwiki          SoftWiki 代码 + compose
/opt/aitools/apps/softwiki/workspace/team
/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode
/opt/aitools/apps/hermes            Hermes 数据 + config + .env
```

### 1.2 依赖

- Docker 28+
- Docker Compose（157 使用 `/usr/local/bin/docker-compose` v5.6.1）
- Python 3.14（SWAgent 容器内已有）
- opencode 1.19.5（pinned）
- Hermes 官方镜像 `nousresearch/hermes-agent:latest`

### 1.3 端口

| 端口 | 服务 | 暴露 |
|---|---|---|
| 6108 | SoftWiki Web | 团队 |
| 6200 | SoftWiki API | 仅本机 |
| 6100 | SoftWiki MCP | 团队 Agent |
| 6111 | SWAgent UI | 团队（当前停用） |
| 9119 | Hermes WebUI | 团队（basic auth） |
| 8642 | Hermes Gateway | 仅本机 |

---

## 2. 从零安装 SoftWiki

> 当前 157 已部署；以下是重建/新机流程。

### 2.1 取代码

```bash
sudo mkdir -p /opt/aitools/apps/softwiki
sudo chown -R "$USER:$USER" /opt/aitools/apps/softwiki

git clone ssh://git@10.3.9.19:2222/faye/softwiki.git \
  /opt/aitools/apps/softwiki
```

如果目标机没有 Forgejo key，用本地打包/rsync 同步；不要用公开仓库替代。

### 2.2 `.env`

```bash
cd /opt/aitools/apps/softwiki
cp config.example.yaml .env.example 2>/dev/null || true
```

需要写入的变量（值不要提交）：

```dotenv
# LLM / embedding
OPENAI_API_KEY=
OPENAI_API_BASE=
EMBEDDING_PROVIDER=
EMBEDDING_MODEL=
EMBEDDING_API_KEY=
EMBEDDING_API_BASE=

# SoftWiki
DATABASE_URL_TEMPLATE=postgresql://softwiki:<PASSWORD>@postgres:5432/softwiki_team
POSTGRES_PASSWORD=<PASSWORD>
POSTGRES_DB=softwiki_team
SOFTWIKI_ACTIVE_WORKSPACE=team
SOFTWIKI_WORKSPACE=/opt/aitools/apps/softwiki/workspace
SOFTWIKI_ROLE=wiki-study

# 端口
API_HOST_PORT=127.0.0.1:6200
MCP_HOST_PORT=6100
WEB_HOST_PORT=6108

# SWAgent
SWAGENT_URL=http://host.docker.internal:6111
SWAGENT_DEFAULT=wiki-research

# 网络受限时
RAG_ALLOW_BM25_FALLBACK=1
EMBEDDING_MAX_RETRIES=1
EMBEDDING_TIMEOUT_SECONDS=8
```

```bash
chmod 600 .env
```

### 2.3 workspace

```bash
mkdir -p /opt/aitools/apps/softwiki/workspace/team/config
```

至少需要：

```text
workspace/team/
├── config/
│   ├── topics.yaml
│   ├── permissions.yaml
│   ├── model_profiles.yaml
│   └── wiki_interventions.yaml
└── scope.md
```

不要在这里放 `armkb`；157 是空 `team`。

### 2.4 启动容器

```bash
cd /opt/aitools/apps/softwiki
sudo /usr/local/bin/docker-compose --project-name softwiki up -d --build
```

检查：

```bash
sudo /usr/local/bin/docker-compose --project-name softwiki ps
curl -s http://127.0.0.1:6200/api/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:6108/
```

### 2.5 初始化数据库

应用启动时会 `init_tables`。确认：

```bash
curl -s http://127.0.0.1:6200/api/status
```

期望：

```json
{"workspace": "/data/workspace/team", "counts": {"documents": 0, ...}}
```

如果是旧库/新 schema，先备份再迁移：

```bash
sudo docker exec -i softwiki-postgres-1 pg_dump -U softwiki softwiki_team \
  > /tmp/softwiki_team_before_migrate.sql
```

---

## 3. 配置模型与 key

### 3.1 SoftWiki 模型

`workspace/team/config/model_profiles.yaml`：

```yaml
profiles:
  cheap_extraction:
    provider: deepseek
    model: deepseek-v4-flash
    api_base: https://api.deepseek.com/v1
    api_key: ""
    temperature: 0.1
  high_quality_analysis:
    provider: deepseek
    model: deepseek-v4-flash
    api_base: https://api.deepseek.com/v1
    api_key: ""
    temperature: 0.7
  wiki_compilation:
    provider: deepseek
    model: deepseek-v4-pro
    api_base: https://api.deepseek.com/v1
    api_key: ""
    temperature: 0.5
```

key 放在 `.env`，不要写进 YAML 提交：

```dotenv
SHELL_API_BASE=https://api.deepseek.com/v1
SHELL_MODEL=deepseek-v4-flash
SHELL_API_KEY=<157_DEDICATED_KEY>
```

> 157 已移除个人 key；必须用 157 专用 key。没有 key 时不要假装 ingest/ask 可用。

### 3.2 SWAgent 模型

SWAgent 读：

```text
SHELL_MODEL
SHELL_API_BASE
SHELL_API_KEY
```

重启：

```bash
sudo systemctl restart swagent
```

### 3.3 Hermes 模型

`/opt/aitools/apps/hermes/config.yaml`：

```yaml
model:
  provider: deepseek
  default: deepseek-v4-flash
  base_url: https://api.deepseek.com/v1
  api_key: ${DEEPSEEK_API_KEY}
```

`/opt/aitools/apps/hermes/.env`：

```dotenv
DEEPSEEK_API_KEY=<157_DEDICATED_KEY>
HERMES_DASHBOARD=1
HERMES_DASHBOARD_HOST=0.0.0.0
HERMES_DASHBOARD_PORT=9119
HERMES_DASHBOARD_BASIC_AUTH_USERNAME=admin
HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=<CHANGE_ME>
HERMES_DASHBOARD_BASIC_AUTH_SECRET=<RANDOM_32_BYTES>
```

重启：

```bash
sudo docker restart hermes
```

Dashboard：

```text
http://117.133.38.157:9119
```

### 3.4 网络受限

157 不能访问：

```text
api.openai.com
generativelanguage.googleapis.com
```

可以访问：

```text
api.deepseek.com
```

因此：

- LLM 使用 DeepSeek
- embedding 不可达
- 检索使用 **BM25 fallback**
- `/api/index` 仍会建 BM25，不建向量
- 需要向量检索时，配置可达 embedding / 代理

---

## 4. 角色与权限

### 4.1 四角色

```text
wiki-study    只读
wiki-work     只读 + Wiki + ingest/index（team trial）
wiki-manage   内容管理 + publish + adjudicate
wiki-admin    全部
```

### 4.2 mapping 文件

```text
workspace/team/config/permissions.yaml
```

示例：

```yaml
version: 1
roles:
  wiki-study:
    allow: ["read.*"]
  wiki-work:
    allow: ["read.*", "wiki.build", "wiki.preview", "ingest.write", "index.write"]
  wiki-manage:
    allow: ["read.*", "wiki.build", "wiki.preview", "wiki.apply",
            "ingest.write", "index.write", "document.delete",
            "conflict.adjudicate", "nli.scan"]
  wiki-admin:
    allow: ["*"]
```

改完重启 API/MCP：

```bash
sudo /usr/local/bin/docker-compose --project-name softwiki restart api mcp
```

### 4.3 角色入口

- Web：左侧角色选择器 → cookie `softwiki_role`
- MCP：`X-SoftWiki-Role: wiki-work`
- CLI/opencode：`SOFTWIKI_ROLE=wiki-work`
- 无 key；内部信任；header 可伪造；对外必须加 token/TLS

---

## 5. 建立 topic

### 5.1 先选 topic

好 topic 的标准：

- 100+ 有营养来源
- 有事实/冲突/版本
- 非过专业
- 可以持续维护
- 有视觉/叙事/演示价值

建议候选：

```text
Coffee — From Bean to Cup
AI — How It Works and How It Got Here
Tea
Chili peppers
Olive oil
```

### 5.2 topic YAML

`workspace/team/config/topics.yaml`：

```yaml
topics:
  coffee:
    name: Coffee
    kind: page
    category: Food & Culture
    subcategory: Beverages
    aliases:
      - coffee-*
      - espresso-*
      - arabica-*
      - robusta-*
    nav: true
    scope: >
      Coffee species, origins, processing, roasting, brewing,
      sensory, health, history, sustainability.
```

字段：

| 字段 | 说明 |
|---|---|
| `name` | 展示名 |
| `kind` | `page` / `category` / `subcategory` |
| `parent` | 分类父节点 |
| `aliases` | 把 raw claim topic 合并到页面 |
| `nav` | 是否出现在导航 |
| `no_docs` | 暂无文档，先占位 |
| `scope` | 该页面范围 |

### 5.3 分类

至少三级：

```text
Food & Culture
  └─ Beverages
       └─ Coffee
```

页面数量不要一次铺 100 个；先 5–10 个策展页。

### 5.4 覆盖率

```bash
curl -s http://117.133.38.157:6200/api/wiki/coverage | python3 -m json.tool
```

看：

- mapped claims
- ignored claims
- top unmapped topics

未映射多时：

- 加 alias
- 加新 canonical page
- 或加入 `__ignore__`（法务/模板）

### 5.5 生成 Wiki

```bash
curl -X POST http://127.0.0.1:6200/api/wiki/build \
  -H 'Content-Type: application/json' \
  -H 'X-SoftWiki-Role: wiki-work' \
  -d '{"topic":"coffee"}'
```

或 Web → Wiki → Generate。

---

## 6. 抓取与导入

### 6.1 目标

建议 **100–150 篇**，不是 1000 篇。质量优先。

分层：

```text
25 行业/标准
25 研究/健康
25 书/长文
25 产地/机构/文档
20 历史/文化
10 经济/可持续
```

### 6.2 来源纪律

- 优先一手来源：标准、论文、官方文档、书籍、博物馆、协会
- 避免 SEO 内容农场、纯营销页、无作者页面
- 记录 URL、标题、作者、日期、来源类型
- 同一内容多 URL：只保留一个 canonical
- 每个 topic 先做 20 篇试跑，再扩到 100

### 6.3 导入方式

#### API

```bash
curl -X POST http://127.0.0.1:6200/api/ingest/url \
  -H 'Content-Type: application/json' \
  -H 'X-SoftWiki-Role: wiki-work' \
  -d '{"url":"https://example.com/article","source_id":"coffee-web"}'
```

PDF：

```bash
curl -X POST http://127.0.0.1:6200/api/ingest/file \
  -H 'X-SoftWiki-Role: wiki-work' \
  -F 'file=@/path/to/doc.pdf' \
  -F 'source_id=coffee-pdf'
```

#### Hermes / MCP

Hermes 已配置：

```yaml
mcp_servers:
  softwiki:
    url: http://host.docker.internal:6100/mcp
    headers:
      X-SoftWiki-Role: wiki-work
    timeout: 600
```

让 Hermes 调：

```text
softwiki_ingest_url
softwiki_ingest_file
```

### 6.4 导入后必须 index

ingest 只建 Document + 后台抽取；不会自动切 chunk/建索引。

```bash
curl -X POST http://127.0.0.1:6200/api/index \
  -H 'X-SoftWiki-Role: wiki-work'
```

期望：

```json
{"status":"success","indexed_chunks":N,"vector_index":false,"bm25_index":true}
```

157 上 `vector_index=false` 是预期；BM25 可用。

### 6.5 批量

- 小批：10–20 篇/批
- 每批后 `/api/index` + 检查 claims
- 不要一次 ingest 上千 PDF
- 失败重试前先看文档状态

---

## 7. Claim / 冲突 / 裁定

### 7.1 状态

```bash
curl -s http://127.0.0.1:6200/api/status
curl -s http://127.0.0.1:6200/api/knowledge/metrics
```

### 7.2 冲突扫描

```bash
curl -X POST http://127.0.0.1:6200/api/conflicts/scan \
  -H 'X-SoftWiki-Role: wiki-manage' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

### 7.3 NLI

dry-run：

```bash
curl -X POST http://127.0.0.1:6200/api/knowledge/nli/scan \
  -H 'Content-Type: application/json' \
  -d '{"limit":10,"apply":false}'
```

apply：

```bash
curl -X POST http://127.0.0.1:6200/api/knowledge/nli/scan \
  -H 'X-SoftWiki-Role: wiki-manage' \
  -H 'Content-Type: application/json' \
  -d '{"limit":10,"apply":true}'
```

NLI 结果缓存，不要重复烧 token。

### 7.4 人工裁定

Web → **Conflicts**：

```text
accept A/B
keep both
mark error
needs evidence
reopen
```

裁定会：

- 写 claim status
- 写 audit
- reproject Graph/Timeline
- 标记 Wiki stale
- enqueue rebuild

---

## 8. Wiki

### 8.1 生成/重建

```text
Web → Wiki → Generate / Regenerate
POST /api/wiki/build
```

当前 12 个策展页；Tier 2 未做。

### 8.2 Stale / rebuild

claim 变化、裁定、冲突扫描会标记 stale；worker 自动重建。

```bash
curl -s http://127.0.0.1:6200/api/wiki/rebuild-tasks
curl -X POST http://127.0.0.1:6200/api/wiki/rebuild-stale \
  -H 'X-SoftWiki-Role: wiki-work'
```

### 8.3 History

```bash
curl -s http://127.0.0.1:6200/api/wiki/history/coffee
```

### 8.4 Prompt Studio

```text
Wiki → Prompt Studio
Preview（只写 preview）
Apply（写 canonical）
```

提示词是表现层，不是事实来源。

---

## 9. SWAgent

### 9.1 当前

- 157：`swagent.service`（容器），当前停用等 key
- javis：`softwiki-agent-web.service`，6111
- engine：opencode 1.19.5
- 入口：`http://<host>:6111` / Web `/swagent`

启动：

```bash
sudo systemctl start swagent
sudo systemctl status swagent
```

### 9.2 Session

- Web chat session 当前在 localStorage
- Agent session 映射 opencode session
- SWAgent 与 personal opencode 使用不同 XDG data
- 不要把 personal opencode 的 session 和 SWAgent 混用

### 9.3 角色

- SWAgent 默认只读 `wiki-research`
- 需要写时用 TUI / mode 切换
- MCP 角色 header 由配置决定

---

## 10. Hermes

### 10.1 启动

```bash
sudo docker ps --filter name=hermes
sudo docker logs --tail=100 hermes
```

### 10.2 Dashboard

```text
http://117.133.38.157:9119
```

用户名 `admin`；密码：

```bash
grep HERMES_DASHBOARD_BASIC_AUTH_PASSWORD /opt/aitools/apps/hermes/.env
```

> basic auth 只适合内部/VPN；不要裸公网。

### 10.3 MCP 验证

```bash
sudo docker exec -i hermes hermes mcp test softwiki
```

期望：

```text
✓ Connected
✓ Tools discovered: 16
```

### 10.4 让 Hermes 文档输入

Hermes 角色 `wiki-work`，可以：

```text
softwiki_ingest_url
softwiki_ingest_file
softwiki_search
softwiki_ask
```

导入后仍然要 `/api/index`。

---

## 11. 运维

### 11.1 状态

```bash
cd /opt/aitools/apps/softwiki
sudo /usr/local/bin/docker-compose --project-name softwiki ps
curl -s http://127.0.0.1:6200/api/health
curl -s http://127.0.0.1:6200/api/status
sudo systemctl status swagent
sudo docker ps --filter name=hermes
```

### 11.2 日志

```bash
sudo /usr/local/bin/docker-compose --project-name softwiki logs -f api
sudo /usr/local/bin/docker-compose --project-name softwiki logs -f mcp
sudo journalctl -u swagent -f
sudo docker logs -f hermes
```

### 11.3 重启

```bash
sudo /usr/local/bin/docker-compose --project-name softwiki restart api mcp web
sudo systemctl restart swagent
sudo docker restart hermes
```

### 11.4 备份

```bash
# workspace
tar -C /opt/aitools/apps/softwiki -czf /tmp/workspace-$(date +%F).tgz workspace

# postgres
sudo docker exec -i softwiki-postgres-1 pg_dump -U softwiki softwiki_team \
  | gzip > /tmp/softwiki_team-$(date +%F).sql.gz
```

恢复前停 API/MCP。

### 11.5 升级 opencode

```bash
./scripts/install-opencode.sh 1.20.0 x64
# 改 service BIN / EXPECTED_VERSION
sudo systemctl daemon-reload
sudo systemctl restart swagent
```

先保留旧版本目录，失败可回滚。

---

## 12. 验收清单

### 12.1 基础

```text
[ ] Web 6108 200
[ ] API 6200 health 200（仅本机）
[ ] MCP 6100 /mcp 可达
[ ] Hermes 9119 login 200
[ ] MCP softwiki 16 tools
[ ] workspace = team
[ ] armkb 不在 157
```

### 12.2 数据

```text
[ ] ingest 1 篇
[ ] document status completed
[ ] /api/index 200（BM25 true）
[ ] search 有结果
[ ] ask 有引用
[ ] claims > 0
[ ] wiki build 成功
[ ] conflict queue 可见
```

### 12.3 角色

```text
[ ] wiki-study ingest 403
[ ] wiki-work ingest 放行
[ ] wiki-manage adjudicate 放行
[ ] wiki-admin 全部
```

---

## 13. 故障排查

### API unhealthy

```bash
sudo /usr/local/bin/docker-compose --project-name softwiki logs --tail=100 api
sudo /usr/local/bin/docker-compose --project-name softwiki ps
```

检查：

- `.env` 是否有空 key
- Postgres 是否 healthy
- `DATABASE_URL_TEMPLATE` 是否指向 `softwiki_team`
- 是否磁盘满

### `no such table/column`

- 应用启动会 `init_tables`
- 旧库需迁移/备份
- 不要手动删表

### MCP 60s timeout

- SWAgent `SWAGENT_MCP_TIMEOUT_MS=600000`
- Hermes `timeout: 600`
- `softwiki_ask` 在 BM25 模式下可能 1–3 分钟

### OpenAI/Gemini timeout

- 157 网络不通
- 用 DeepSeek
- embedding 不可达时 BM25 fallback
- 不要反复重试

### Hermes dashboard 302

- 正常：跳 `/login`
- 用 basic auth 登录
- 非 loopback 必须有 auth provider

### Hermes MCP 连接失败

```bash
sudo docker exec -i hermes hermes mcp test softwiki
```

检查：

- SoftWiki MCP 容器 6100
- `host.docker.internal:host-gateway`
- header `X-SoftWiki-Role`
- 6100 是否被防火墙拦

### 403 role

- Web cookie `softwiki_role`
- MCP header
- `permissions.yaml`
- 重启 API/MCP

### ingest 重复

- 同 hash 跳过
- 同 URL 同内容跳过
- 同 URL 新内容建新版本

### Wiki empty

- topic 是否有 canonical claims
- alias 是否覆盖 raw topic
- 是否 stale
- `WIKI_MAX_CLAIMS`

---

## 14. 安全

- 不要提交 `.env` / key / 密码
- 不要公网裸露 6200/6100/6111/9119
- 9119 至少 basic auth + 安全组/VPN
- 6108 默认角色 `wiki-study`，但可伪造
- MCP 角色 header 可伪造
- API 仅 127.0.0.1
- 对外前加 TLS / 反代 / token

---

## 15. 给 opencode 的执行提示

当用户问“怎么安装/怎么建 topic/怎么导入/怎么修”时：

1. 先读本手册对应章节。
2. 先跑状态命令，再改配置。
3. 不猜路径；先 `ls` / `docker ps` / `curl`。
4. 不打印密钥。
5. 破坏性操作先备份。
6. 改完必须验证：
   - health
   - status
   - MCP test
   - 一次 ingest/index/search
7. 若与本文不一致，以 `docs/` 最新文档和 `progress.md` 为准，并更新本文。

---

## 16. 当前已知边界

- 157 没有 `armkb`
- 157 没有个人 LLM key（等专用 key）
- 157 无法访问 OpenAI/Gemini
- embedding 不可达，BM25 fallback
- SWAgent 当前停用
- Web session 仍是 localStorage，服务端 session 未做
- 角色是信任型自报，不是认证
- Wiki Tier 2 未做
- Graph/Timeline 版本链/evidence 多对多未完成
- 近重复文档只报告，不自动合并
