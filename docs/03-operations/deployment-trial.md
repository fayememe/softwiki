# Deployment — trial.example.internal（team trial）

> 2026-11-01
> 目标：只部署 SoftWiki；**不部署 `kb-alpha`**。新知识库后续单独建。

## 两个知识库

| KB | Web | MCP | API | database |
|---|---|---|---|---|
| `coffee-kb` | 6108 | 6100 | 127.0.0.1:6200 | `softwiki_coffee` |
| `ai-history-kb` | 6109 | 6102 | 127.0.0.1:6202 | `softwiki_ai_history` |

`team` 已删除；`kb-alpha` 未部署。

语料目标：每个 KB **100–200 篇**，按 **150 篇/库**推进；先各 20 篇 pilot。

## 入口

```text
Coffee Web:      http://trial.example.internal:6108
AI History Web:  http://trial.example.internal:6109
Coffee MCP:      http://trial.example.internal:6100/mcp
AI History MCP:  http://trial.example.internal:6102/mcp
Coffee SWA:      http://trial.example.internal:6111
AI History SWA:  http://trial.example.internal:6112
Coffee API:      http://127.0.0.1:6200
AI History API:  http://127.0.0.1:6202
```

API 已绑定 `127.0.0.1:6200`，不公网暴露。

## 机器 / 路径

```text
用户：operator
代码：/opt/aitools/apps/softwiki
workspace：/opt/aitools/apps/softwiki/workspace/{coffee,ai-history}
数据库：softwiki_coffee / softwiki_ai_history
Docker：28.5.2
Compose：/usr/local/bin/docker-compose v5.6.1
```

## 更新代码（手动，无 CI）

目标机没有 CI timer，且到 Forgejo（`10.3.9.19:2222`）不通，必须从开发机推代码。

```bash
# 开发机：只打包代码，排除 node_modules/.next/workspace
tar -czf /tmp/deploy-src.tgz --exclude=__pycache__ --exclude='*.pyc' \
  --exclude=web/node_modules --exclude=web/.next \
  softwiki web pyproject.toml Dockerfile
cat /tmp/deploy-src.tgz | ssh faye@118.193.105.3 \
  'cd /opt/aitools/apps/softwiki && tar -xzf -'

# trial-host：sudo 不继承 PATH，docker-compose 要写全路径
cd /opt/aitools/apps/softwiki
sudo /usr/local/bin/docker-compose -f docker-compose.yml build api web
sudo /usr/local/bin/docker-compose -f docker-compose.yml -p softwiki up -d --no-build --remove-orphans
sudo /usr/local/bin/docker-compose --env-file .env.ai -f docker-compose.yml -p softwiki-ai up -d --no-build --remove-orphans
sudo systemctl restart swagent-coffee swagent-ai   # swagent 用 softwiki-api:latest，必须重启换镜像
```

验证：

```bash
curl -s http://127.0.0.1:6200/api/agent/status; curl -s http://127.0.0.1:6202/api/agent/status
timeout 12 curl -s -N 'http://127.0.0.1:6108/api/agent/events?session_id=probe' | grep -m1 '^data:'
timeout 12 curl -s -N 'http://127.0.0.1:6109/api/agent/events?session_id=probe' | grep -m1 '^data:'
```

- 回滚：`backup-images-<ts>.txt` 里有旧 image id，`docker tag <id> softwiki-api:latest` 后重新 `up -d`；源码在 `backup-src-<ts>.tgz`。
- `curl -i ... | head -8` 只会看到响应头（第 9 行才是 `data:`），别误判成没有事件。
- 2026-11-10：`.env.ai` 的 `AGENT_WEB_URL` 原为 6111（coffee），已改为 6112。

## 当前状态

```text
coffee-kb:      documents 185 / chunks 3,489 / claims 6,691 / relationships 8,179 / events 2,297
ai-history-kb:  documents 160 / chunks 5,497 / claims 9,526 / relationships 12,067 / events 3,279
```

- `team` 已删除
- `kb-alpha` 未部署
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
Dashboard：http://trial.example.internal:9119
Gateway：http://127.0.0.1:8642（仅本机）
数据：/opt/aitools/apps/hermes（挂载 /opt/data）
版本：0.22.5
模型：deepseek-v4.1-flash（trial-host oneroute key 已配置；不使用个人 DeepSeek key）
```

Dashboard 使用 basic auth（用户名 `admin`；密码见目标机
`/opt/aitools/apps/hermes/.env`，不要提交到 git）。

> 2026-11-01 更新：已从 trial-host 移除个人 DeepSeek/OpenAI/embedding key；SoftWiki
> `model_profiles.yaml` 的 `api_key` 已置空。需要 trial-host 专用 key 后再启用 LLM。
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

## 2026-11-19 部署：身份 / 审计 / 建库向导 / 图谱重写

### 本次新增的内容

| 类别 | 内容 |
|---|---|
| 权限 | 角色 fail-closed（拼错回退 `wiki-study`）、降级工作模式、审计日志 |
| 身份 | `softwiki/identity/`（OIDC + 微信 adapter、本地用户表、超级用户窗口、三态） |
| 接口 | `/api/auth/*`、`/api/admin/*`、`/api/kb/templates|create|registry`、`/api/graph/overview|subgraph` |
| 知识库 | `config/kbs.yaml` 注册表；仓库 `kb-templates/` |
| WebUI | 「新建库」面板、图谱页 Canvas 重写 |
| 依赖 | **无新增**，`pyproject.toml` 与旧版一致 |

`off` 模式（当前 trial-host 的状态）行为不变：仍是单机管理员，不需要登录。
所有 `SOFTWIKI_AUTH_MODE` 相关能力默认不启用。

### 构建遇到的坑

`docker-compose build api` 卡在 `pip install -e .`，约 8 分钟后报
`ResolutionImpossible`，而 `pyproject.toml` 与 9 天前成功构建时**完全一致**
（说明不是依赖变更导致，是解析/镜像源问题）。本次改用
`deploy/Dockerfile.api-fast`：以已验证的旧镜像为依赖层，只覆盖源码。
`pip install -e .` 留下的 editable 安装指向 `/app`，覆盖源码即可生效，无需重装。

```bash
# 保留可回滚的依赖层
sudo docker tag softwiki-api:latest softwiki-api:base-20261119
# 只换源码
sudo docker build -f deploy/Dockerfile.api-fast -t softwiki-api:latest .
```

依赖解析问题**未定位**，下次需要真正重建依赖时再查。

### 卡死的容器（已解决 2026-11-20）

重建过程中 `softwiki-ai-api-1` 停在 `zap_pid_ns_processes`（PID 1 无法被回收），
`docker rm -f`、`ctr tasks kill` 均无效，重命名为 `softwiki-ai-api-1-stuck` 后
仍占用 `127.0.0.1:6202`；ai-history 的 API 曾临时改绑 `6212`。

**清理办法（需要在无业务时段做）**：

1. `sudo systemctl restart docker` —— 释放网络命名空间（端口随之空闲），
   `unless-stopped` 的容器自动回来；swagent 由 systemd 拉起。
2. **仅重启 docker 不够**：卡死 task 由独立的 `containerd-shim` 持有，
   daemon 重启不会回收它。定位后单独杀掉：
   ```bash
   ps -eo pid,cmd | grep containerd-shim | grep <container-id>
   sudo kill -9 <shim-pid>
   ```
3. `docker rm -f softwiki-ai-api-1-stuck` 即可删除记录。

**经验**：容器卡在 `zap_pid_ns_processes` 时，`docker rm -f` 和 `ctr tasks kill`
都会失败；真正的持有者是 shim 进程。**不要**为此重启整个 containerd
（会影响该机上所有容器），杀掉单个 shim 就够。

清理后 ai 栈已交还 compose 管理（`-p softwiki-ai`），API 回到 `6202`。

### 验收结果（2026-11-19 部署 + 2026-11-20 重启复核）

```text
coffee api 6200 200 | ai api 6202 200
coffee web 6108 200 | ai web 6109 200
coffee mcp 6100 200 | ai mcp 6102 200
coffee swa 6111 200 | ai swa 6112 200
graph overview 200  | /api/kb 200
hermes 9119 302->login 200 | agent-portal running
```

数据完整性（重启前后一致）：

```text
coffee:      documents 185 / chunks 3,489 / claims 6,691 / entities 6,005 / relationships 8,179 / events 2,297
ai-history:  documents 160 / chunks 5,497 / claims 9,526 / entities 9,232 / relationships 12,067 / events 3,279
```

- `/api/ask` 两个库均返回带页码引用与 `citation_check` 的答案。
- 审计日志落在 `/opt/aitools/apps/softwiki/workspace/.softwiki-audit/audit.log`，
  已确认记录的是**实际生效角色**（`wiki-admin`），不是环境变量里的 `wiki-study`。
- 建库向导 dry-run 返回完整文件计划，未落盘。

### 2026-11-20 部署：多 KB 可用性 + LLM-Wiki 一实体一页 + 导航重构

**本次上线内容**

| 类别 | 内容 |
|---|---|
| 多 KB | `/api/kb?verify=true` 探测本实例能否服务该库（缓存 15s / 超时 3s）；`meta.yaml: web_url`；库选择器改为数据驱动 |
| LLM-Wiki | `softwiki/wiki/subject_pages.py`：一实体一页、固定 25 条上限、超限拆页不静默截断；`/api/wiki/pages*`；WebUI **LLM Wiki** 面板 |
| 导航 | 侧栏分五组（Home / Knowledge / Assist / Contributor / Admin），角色驱动可见性；`wiki` 面板下线，`wikipages` 更名 **LLM Wiki** |
| 列表 | documents / claims / LLM Wiki 全部服务端分页（50/页）；徽章显示完整数字；表格列宽与行距收紧 |
| 管理面 | `AdminPanel`：用户列表（角色覆盖 / pending 放行 / `kb_scope` 可见数）+ 审计日志 |

**验收（2026-11-20）**

```text
容器 8 个全部 healthy（api/web ×2、mcp ×2、postgres ×2）
coffee api 6200 200 | ai api 6202 200
coffee web 6108 200 | ai web 6109 200
coffee mcp 6100 initialize 200 | ai mcp 6102 initialize 200
```

**库隔离（同日二次修正）**：此前两栈挂载同一个 workspace 根，导致
「数据库隔离、文件不隔离」。已改为每栈私有根，详见
[`docs/02-design/multi-kb.md`](../02-design/multi-kb.md) §7。

```text
6200 /api/kb?verify=true -> active=coffee      kbs=[('coffee', True)]
6202 /api/kb?verify=true -> active=ai-history  kbs=[('ai-history', True)]
6200 ask(kb="ai-history") -> HTTP 404 "Knowledge base 'ai-history' not found"
softwiki-api-1: ls /data/workspaces/ai-history -> No such file or directory
6108 /wikiweb/ai-history/index.html -> 404
```

挂载现状：

```text
softwiki-api-1     workspace/stacks/coffee -> /data/workspaces
                   workspace/config        -> /data/workspaces/config
                   workspace/.softwiki-audit -> /data/workspaces/.softwiki-audit
softwiki-ai-api-1  workspace/stacks/ai     -> /data/workspaces
                   （config / audit 同样共享）
```

数据完整：coffee 185 docs / 6,686 claims；ai-history 160 docs / 9,514 claims。

LLM-Wiki 页面：

```text
6200: 45 subjects（28 个超限已拆页）
6202: 40 subjects（27 个超限已拆页）
抽检 Arabica 266/266 claims / 11 页，Australia 34/34 / 2 页，无静默丢弃
```

UI（headless Chrome）：库选择器只列本栈的库（各 1 项），无「不可用」提示，
`pageErrors=[]`。

数据库清理：删除空残留库 `softwiki_ai`（`public` schema 0 张表、无对应目录）。

**扩容实测**：ai 栈在库根下新建目录 + `CREATE DATABASE softwiki_<kb>` →
`/api/kb?verify=true` 立刻可见并 `available=true`（验证后已删除）。

> 结论：**每个栈独立服务自己的库集**，加库不需要改代码；跨栈不可达（文件与
> 数据库都不可达），这是刻意的隔离边界。

### 线上已知故障（2026-11-20，非本次改动）

`oneroute` 的 `/v1/embeddings` 返回 `Error code: 504`，**单次耗时 185 秒**才失败：

```text
[rag] embedding unavailable, using BM25 only: Error code: 504
```

后果：`/api/ask` 先等 embedding 超时再降级 BM25，实测 200s 未返回；
新文档入库无法向量化。同一时刻 chat completions 正常（8.6s）。

用 `git stash` 对照确认与本次改动无关。临时办法是换 embedding 供应商，
或用本机 Ollama 的 `nomic-embed-text`。

### 2026-11-20 修复：Wiki Portal 404 / 移除 SWAgent 入口

**`/wikiweb` 404 的原因**：这个路由只在 trial-host 上被临时加过，从未进入本仓库。
本次从仓库源码重建镜像后，路由和静态内容一起消失。

**修法（2026-11-20 第二轮：按库分离）**：

- 新增 `web/app/wikiweb/route.ts`：把 `/wikiweb` 307 到 `WIKIWEB_ENTRY` 指定的页面。
- 门户是**生成产物**，不进仓库，改为**放进各自的 workspace**：

  ```text
  workspace/coffee/exports/wikiweb/
  ├── assets/          # wiki.css / wiki.js
  └── coffee/          # 站点本体（index / all / about / category / timeline）
  workspace/ai-history/exports/wikiweb/
  ├── assets/
  └── ai-history/
  ```

- compose 每个 web 容器只挂自己库的目录：
  `${WIKIWEB_DIR}:/app/public/wikiweb:ro`，`WIKIWEB_ENTRY` 指向本站入口。
  `.env` → `coffee/index.html`，`.env.ai` → `ai-history/index.html`。
- 站点内部使用**层级相对路径**（`../assets/`、`../../assets/`），所以库目录必须保持在挂载根下一层，
  不能把 `coffee/*` 直接摊到根上。

**为什么必须按库拆**：原来是一个共用站点，落地页同时列出两个库 —— 打开 6108 的人能点进
ai-history，绕过了 `kb_scope`。拆开后 `6108/wikiweb/ai-history/...` 直接 404。

验证：

```text
6108 /wikiweb                       307 -> /wikiweb/coffee/index.html
6108 /wikiweb/coffee/index.html     200
6108 /wikiweb/assets/wiki.css       200
6108 /wikiweb/coffee/category/concept.html 200  84,298B
6108 /wikiweb/ai-history/index.html 404   ← 隔离生效
6109 /wikiweb                       307 -> /wikiweb/ai-history/index.html
6109 /wikiweb/coffee/index.html     404   ← 隔离生效
```

浏览器实测：落地页 `data-kb` 分别为 Coffee / AI History，无对方链接，CSS 生效，
页内搜索各返回 8 条，无 pageerror。

旧的共用副本（20MB）已改名为 `wikiweb.old-20261120/`，可删。

**未来**：门户目前是静态快照，Wiki 改了不会自动更新 —— 缺一个生成器（`softwiki wiki site`），
见 NEXT。

**移除 SWAgent 入口**：侧栏底部的 `SWAgent ↗` 与聊天页头部的 `Agent ↗` 都已删除；
聊天里 `Quick / SWAgent` 的模式切换保留（那是功能本身，不是入口）。
`/swagent` 路由与 `swagent-*` systemd 服务仍在，是否退役另行决定。

### 上线后待测（未在本轮验证）

- 浏览器里图谱页的交互（缩放/拖拽/双击展开）与不卡顿
- WebUI「新建库」面板的真实点击流程（只会跑过 API 层）
- SWAgent 真机对话（只验证了 `/api/agent/status`）
- 两库的 Wiki / Conflicts / Report 页面回归

### 2026-11-20 修复：图谱拖拽导致页面报错

**现象**：拖拽图谱即整页报错。

**根因**：`GraphPanel` 在 `setNodes`/`setView` 的更新函数里读
`dragRef.current!.dx` / `panRef.current!.tx`。React 可能在你松手之后才执行该更新函数，
此时 ref 已被 `onPointerUp` 置空 —— `null.dx` 直接抛异常。
构建和类型检查都通过，这是纯运行时错误。

**顺带修掉的三个问题**：

1. `settle` 是 effect 内局部变量，而 effect 依赖 `hovered`/`selected`：鼠标每划过一次
   就把力导向布局重启一遍，节点会跳。改为 ref，循环只启动一次。
2. 拖拽时每次 `pointermove` 都 `setNodes`，会重渲染整个侧栏（最多 300 项）。
   改为拖拽期间直接改坐标、松手时提交一次。
3. 滚轮 `preventDefault` 在 React 的被动监听器里无效（控制台报错且页面照旧滚动）。
   改为原生 `addEventListener('wheel', ..., { passive: false })`。

另外「隐藏未展开」改为按存活节点过滤边，指针离开画布时清理拖拽状态。

**验证**：新增 `scripts/ui-smoke.mjs`，用真实浏览器（headless Chrome）跑
拖拽 / 缩放 / 侧栏聚焦 / 展开 / 双击 / 隐藏 / 重置 / 搜索 + 建库 dry-run：

```bash
npm i puppeteer-core                    # 不必装进项目依赖
PUPPETEER_DIR=$(pwd) node scripts/ui-smoke.mjs http://127.0.0.1:16108/
```

2026-11-20 两库实测结果：`nodeDrag=true`、`canvasStillThere=true`、
`pageErrors=[]`、`consoleErrors=[]`、`hasErrorOverlay=false`、
建库预览与校验均正常。

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
- `kb-alpha` 仍在 build-host；本机不再有 `kb-alpha`。
- `team` 已删除；不要再把 `swagent` 指回 `team`。
- 2026-11-02 pilot 因 trial-host 出口封锁只入库 12 篇（4 + 8），已由「本地抓取 + 远侧入库」弥补，见下节。
- 目标机不要直接抓外网 URL 入库（见「出口封锁实测」）。

## 语料构建管线（2026-11-03）

trial-host 的出口限制无法绕过 DNS 修好，改为**在开发机抓正文、以 markdown 推送入库**。

```bash
# 1. 本地抓取（front matter 带 title/author/date/url）
python scripts/trial_fetch.py --kb coffee --out /tmp/trial/coffee \
    --sources wiki,rss,urls,europepmc --target 190
python scripts/trial_fetch.py --kb ai-history --out /tmp/trial/ai-history \
    --sources wiki,urls,rss --target 185

# 2. 打包推到目标机
tar -czf - -C /tmp/trial coffee | ssh operator@trial.example.internal 'tar -xzf - -C /tmp/trial-ingest'

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

- trial-host 无全局 IPv6，无 `*_PROXY`；AliDNS DoH 返回的也是污染结果，Cloudflare DoH 不可达。
- 可达且已在使用：`en.wikipedia.org`（仅开发机）、ar5iv、SEP、Europe PMC、dailycoffeenews、baristamagazine、coffeegeek、IEEE Spectrum、MIT Tech Review、computerhistory.org。
- 排除：Guardian / NewYorker / Atlantic / BBC / ai.stanford.edu（TCP 封锁）、perfectdailygrind（feed 403）、science.org / smithsonianmag（403，UA 可解但未采用）。

### 已知缺口

- markdown 文档没有页码，`/api/ask` 的 `page_start` 为 `None`；页码引用只在 PDF 上有意义。
- ai-history 的 RSS 稿件里约 20 篇被 `scope_guard` 判为越界（企业治理、预测类新闻），因此 184 篇只入库 160。

---

## 前端汉化（i18n）实测（2026-11-17）

> 中国侧（trial-host）直接在目标机源码上加了前端 i18n。**未入库**：目标机目录不是 git 仓库，唯一备份是 `backup-20261116/web-src-bak-20261116-1030.tgz`（约 246MB，只含 `web/`）。

### 实现方式

- 新增 `web/lib/i18n/index.tsx`：
  - `zh` / `en` / `ja` 三份字典；`en` 定义 key 模板（`Dict = typeof en`，类型层面强制另外两份结构一致）；
  - 默认 `zh`；`localStorage['softwiki_locale']` 持久化；`t('a.b.c', { n })` 点路径 + `{placeholder}` 插值；缺 key 回退英文再回退 key；挂载后同步 `<html lang>`。
- 新增 `web/components/LanguageSwitcher.tsx` + `.module.css`：侧边栏头部地球按钮，按 `zh → en → ja` 轮换。
- `app/page.tsx` 外层包 `I18nProvider`；`New Chat` 改为哨兵常量 `NEW_CHAT_NAME`，渲染时按语言翻译（旧会话数据仍兼容）。
- 19 个既有组件 / 聊天 hook 全部改为 `useT()`（Sidebar、ChatPanel、ChatMessage、Claims、Conflicts、Dashboard、Documents、Graph、Ingest、Timeline、Wiki、SourceDrawer、GlobalSearch、RoleSelector、KnowledgeBaseSelector、AgentMessageView、ToolCard、useAgentChat），合计约 730 行改动。
- 字典共 **311 个 key**；实测 zh / ja 与 en **key 完全对齐、`{n}` 占位符完全对齐**；组件里 254 个静态 `t()` key 全部存在；只有 `SWAgent` 保留英文。
- 译文是手写、术语统一（claim=论断、conflict=冲突、timeline=时间线、wiki 面板=知识库），不是机翻。
- 部署：web 镜像 `softwiki-web:latest`（image id `41150a94b441`，2026-11-16 11:08）已重建，coffee / ai-history 两个 Web 容器都在跑；`curl :6108` 的 SSR 直接输出中文导航，说明构建已包含该改动。

### 覆盖范围与缺口

已覆盖：静态 UI 文案、按钮 / 占位符 / aria / title（除 1 处遗漏）、验证与错误占位文案、引用来源标签、会话日期（昨天 / N 天前）、SWAgent 工具卡片状态。

未覆盖 / 待修：

- `web/app/layout.tsx` 的 `<html lang="en">` 和 `metadata`（title / description / keywords / OG）仍是英文；只在客户端挂载后改 `lang`，首屏 / SEO / 分享卡片仍是英文。
- `web/lib/api.ts` 与后端返回的错误串仍是英文，会原样显示在 UI 错误条。
- 数据本身的英文值不做映射：claim status（`disputed`）、subject / predicate、workflow 名、`Unknown` 哨兵等。
- KB 内容 / 答案 / Wiki 正文语言取决于语料与模型；UI 汉化 ≠ 内容汉化。Wiki 页面要中文需在 Prompt Studio 里明确要求中文输出。
- 新增的 `wikiweb` 静态门户（1,087 个 HTML / 20MB）**全英文**，与 i18n 无关。
- 侧边栏收起时语言切换按钮不可见（收起态仍保留 `title="Expand sidebar"`，且字典里已有 `sidebar.expand` 未使用）。
- 日期用 `toLocaleDateString([])` 跟随浏览器 locale，不跟随所选 UI 语言。
- SSR 默认中文；英文用户首次会先看到中文，localStorage 生效后切回。

### 与 i18n 无关的同批改动

- `docker-compose.yml`：Postgres 默认库名 `softwiki_kb_alpha` → `softwiki_armkb`（疑似旧部署残留）。
- `docker-compose.yml`：web 服务挂载 `./wikiweb:/app/public/wikiweb:ro`。
- 新增 `web/app/wikiweb/route.ts`：`/wikiweb` 307 → `/wikiweb/index.html`。
- 新增 `wikiweb/`：两个 KB 的静态百科门户（1,087 页，英文）。

### 拉取 / 收编

```bash
# 开发机：只拉 web 源码（不含 node_modules / .next）
ssh faye@118.193.105.3 'cd /opt/aitools/apps/softwiki && \
  tar -czf - --exclude=node_modules --exclude=.next \
  web/app web/components web/lib web/package.json web/package-lock.json web/next.config.ts' \
  | tar -xzf - -C /tmp/trial-web
```

建议正式收编时拆两个 commit（「i18n 框架 + 字典」/「组件接线」），先补 `layout` metadata 与 `lang`、`lib/api.ts` 错误串、`Expand sidebar`，再决定是否默认 `zh`。

### 品质独立核查（2026-11-19）

对 trial-host 上的 i18n 实现做了独立评审（不看既有结论，重新验证）：

| 检查项 | 方法 | 结果 |
|---|---|---|
| 字典 key 完整性 | 解析三份字典叶子 key 并与 en 比对 | **311 key，zh/ja 与 en 完全对齐，0 缺失** |
| 调用点覆盖 | 源码中所有 `t('...')` 字面量 vs 字典 | **274 处调用，0 处指向不存在的 key** |
| 未翻译残留 | zh 中与 en 取值相同的条目 | **仅 `SWAgent`（产品名）** |
| 占位符一致性 | `{n}` 等占位符在三种语言间比对 | **0 处不一致** |
| 硬编码中文残留 | 扫描组件源码 | **仅 `LanguageSwitcher` 的「中/日」标签**（合理） |
| 硬编码英文残留 | JSX 文本 / placeholder / title | `Enter`（键盘键名，合理）、`Expand sidebar`（未走 `sidebar.expand`）、`https://example.com/article`（示例 URL） |
| TypeScript 类型 | `tsc --noEmit --strict` 引用 `Dict` 约束 | **零错误** |
| 组件接入率 | 使用 `useT()` 的文件数 | **18 / 21**（未接入的：`layout.tsx`、`LanguageSwitcher.tsx`、`i18n/index.tsx` 本身） |
| 与上游同源度 | 组件名逐一比对 | **15 个组件完全同名，trial 只多 `LanguageSwitcher`** |

**质量结论：实现是合格的，不是机翻拼凑。** 结构（`en` 定义 key 模板 + `Dict` 类型强制另两份对齐）、回退链（当前语言 → en → key 原文）、插值、`localStorage` 持久化、SSR 安全都已经到位。

发现的问题（均为**可修的小缺口**，不是设计错误）：

1. **`t(key: string)` 没有 key 联合类型约束。** 写错 key 不会编译报错，只会在运行时静默显示 key 名。这是可维护性缺陷——将来新增文案写错字无人发现。
2. **`I18nProvider` 挂在 `app/page.tsx`（`'use client'`）**，而不是 `layout.tsx`。后果是：`<html lang>` 与 `metadata` 无法随语言变化，首屏 / SEO / 分享卡片恒为英文。
3. **首屏闪烁**：SSR 用 `DEFAULT_LOCALE='zh'`，但用户若选过 `en`/`ja`，`useEffect` 挂载后才纠正 → **英文用户每次刷新先看到一闪中文**。
4. `lib/api.ts` 与后端错误串未国际化，会原样显示英文。
5. 侧边栏收起时 `Expand sidebar` 未走 `sidebar.expand`（字典里有这个 key）。
6. 日期用浏览器 locale，不跟随所选 UI 语言。

**与上游的关系**：trial-host 的 web 与本仓库同源，组件集合一致，差异约 730 行且几乎全部是 i18n 接线；唯一非 i18n 的功能性改动是新增 `app/wikiweb/route.ts`（静态门户路由，与 i18n 无关，应单独评估是否收编）。

### 收编结果（2026-11-19）

i18n 已收入本仓库，并按「跟随浏览器 + 用户可自选」重做了语言协商：

| commit | 内容 |
|---|---|
| `e5250ce` | `feat(web)` i18n 框架 + 三份字典 + `LanguageSwitcher` + async layout |
| `a70eb9c` | `refactor(web)` 15 个组件 + `app/page.tsx` 接线到 `useT()` |

**相对 trial-host 版本的改动**（修掉品质核查中列出的缺口）：

1. **`lib/i18n/locale.ts` 独立出来**（不带 `'use client'`）。原实现把
   `isLocale` / `negotiateLocale` 放在 `'use client'` 的 `index.tsx` 里，
   Server Component 调用会被 Next 拒绝：
   `Attempted to call isLocale() from the server but isLocale is on the client`。
2. **`app/layout.tsx` 改为 async Server Component**，先读 cookie 再按
   `Accept-Language` 协商，渲染正确的 `<html lang>` 与 `metadata`。
   原实现把 Provider 挂在 `page.tsx`，`<html lang>` 与 metadata 恒为英文。
3. **首屏不再闪烁**：locale 由服务端决定并作为 `initialLocale` 传入。
   原实现 SSR 恒为 `zh`，挂载后才切。
4. **`t()` 加 key 类型约束**（`MessageKey = Leaves<Dict>`），写错 key 会编译报错，
   而不是运行时静默显示 key 名。
5. **语言选择写入 cookie**（`softwiki_locale`，1 年，`samesite=lax`），
   服务端下次直接按 cookie 渲染；cookie 优先于 `Accept-Language`。
6. `page.tsx` 不再重复挂 `I18nProvider`（会遮蔽 layout 的 locale）。
7. `Expand sidebar` 改走 `sidebar.expand`；收起态也显示语言按钮；
   会话日期改用所选语言的 locale。

**验证**（`npm run build` + `next start` 实测）：

```
Accept-Language: zh-CN -> <html lang="zh-CN"> <title>Softwiki — 研究智能中枢
Accept-Language: en-US -> <html lang="en">    <title>Softwiki — Research Intelligence Hub
Accept-Language: ja-JP -> <html lang="ja">    <title>Softwiki — リサーチ・インテリジェンス・ハブ
Accept-Language: fr-FR -> <html lang="zh-CN"> （无匹配，回退默认）
cookie=zh + Accept-Language: ja -> <html lang="zh-CN">  （cookie 优先）
```

页面正文同步正确：zh「主页/对话/导入/论断/时间线/知识库」，
en「Claims/Timeline」，ja「ホーム/チャット/取り込み/論点/競合/タイムライン」。

`tsc --noEmit` 零错误；`npm run build` 通过；`pytest tests -q` 111 passed。

**仍未做**：`lib/api.ts` 与后端返回的错误串未国际化（会原样显示英文）。


