# build-host 部署（Docker Compose + CI/CD）

> 目标：把 softwiki 以 Docker Compose 部署到 `build-host`（`build.example.internal`），由 CI 自动构建、启动、健康检查与回滚。
> 试用阶段与旧 systemd 部署**并行**：旧栈占 `6100/6108/6200`，新栈先用 `6301/6308/6300`，验收后再切。

## 拓扑

| 服务 | 容器端口 | 宿主端口（并行） | 说明 |
|---|---|---|---|
| `api` | 6200 | 6300 | FastAPI REST |
| `mcp` | 6100 | 6301 | MCP（SSE + Streamable HTTP） |
| `web` | 6108 | 6308 | Next.js，`/api` 反代到 `http://api:6200` |

- 数据：`/opt/aitools/apps/softwiki/workspace` → 容器 `/data/workspace`（SQLite 等仍在其中）。
- 密钥：`/opt/aitools/apps/softwiki/.env`（不进镜像、不进 git）。
- 当前活动库：`SOFTWIKI_ACTIVE_WORKSPACE=kb-alpha`（API 可用 `/api/workspace` 切换；MCP 需重启容器才会跟随）。

## 前置

1. build-host 已安装 Docker 26 + Compose 2.26。
2. build-host 的 SSH key 已作为 **read-only deploy key** 加入 Forgejo 仓库 `operator/softwiki`。
3. `/opt/aitools/apps/softwiki/.env` 存在。

验证：

```bash
ssh operator@build-host 'cd ~/mydrv/git/softwiki && git ls-remote origin HEAD'
```

## 首次部署（并行端口）

```bash
ssh operator@build-host
git clone ssh://git@git.example.internal:2222/operator/softwiki.git ~/softwiki-ci
SOFTWIKI_ENV_FILE=/opt/aitools/apps/softwiki/.env \
  ~/softwiki-ci/scripts/ci-deploy.sh
```

脚本会：拉取 `origin/master` → 按 SHA 构建镜像 → `docker compose up -d` → 健康检查 → 写 `.deploy/last-good-sha`。

验收：

```bash
curl -fsS http://127.0.0.1:6300/api/health
curl -fsSI http://127.0.0.1:6308/
nc -z 127.0.0.1 6301 && echo mcp-ok
```

## 切流（停旧 systemd）

验收通过后：

```bash
sudo systemctl stop softwiki-api softwiki-mcp softwiki-web
sudo systemctl disable softwiki-api softwiki-mcp softwiki-web
```

然后把 `deploy/softwiki-deploy.service` 里的端口改为 `6200/6100/6108`，或手动执行：

```bash
API_HOST_PORT=6200 MCP_HOST_PORT=6100 WEB_HOST_PORT=6108 \
SOFTWIKI_ENV_FILE=/opt/aitools/apps/softwiki/.env \
  ~/softwiki-ci/scripts/ci-deploy.sh
```

## CI 定时器

```bash
sudo cp ~/softwiki-ci/deploy/softwiki-deploy.service \
        ~/softwiki-ci/deploy/softwiki-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now softwiki-deploy.timer
journalctl -u softwiki-deploy -f
```

- 轮询周期：3 分钟；`flock` 防止并发。
- `softwiki-deploy.service` 默认使用生产端口 `6200/6100/6108`；并行验证时可覆盖环境变量。
- 状态：`~/softwiki-ci/.deploy/last-deployed-sha`、`last-good-sha`。
- 强制重跑：`FORCE=1 ~/softwiki-ci/scripts/ci-deploy.sh`。

### 坑：CI 静默失败一整天（2026-11-24）

症状：`last-deployed-sha` 停在旧值，而 `journalctl -u softwiki-deploy` 每 3 分钟刷一条：

```
[ci] deploying <sha>
open /home/faye/.docker/buildx/current: permission denied
softwiki-deploy.service: Failed with result 'exit-code'
```

原因：手工排障时用过 `sudo docker build`，把 `~/.docker/buildx/current` 写成了 **root 所有**；
CI 以 `User=faye` 运行，buildx 无法写状态文件，`docker compose build` 第一行就失败。
镜像没换，所以**线上一直跑旧代码，看起来却「CI 正常轮询」**。

```bash
sudo chown -R faye:faye /home/faye/.docker/buildx
sudo systemctl start softwiki-deploy.service   # 立即补一次
```

排查纪律：确认部署是否真的生效，要同时看三个东西 ——
`journalctl -u softwiki-deploy`（有无 FAILURE）、`.deploy/last-deployed-sha`、
`docker images softwiki-api --format '{{.Tag}}'`（tag 应等于当前 HEAD）。
只看 timer 在跳是不够的。

## 回滚

```bash
cat ~/softwiki-ci/.deploy/last-good-sha
cd ~/softwiki-ci
TAG=<sha> docker compose --project-name softwiki up -d --no-build
```

## Embedding（OpenAI）

build-host 的 `.env` 需要独立的 embedding 凭据（不要和 chat 的 Google/DeepSeek key 混用）：

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=100
```

`text-embedding-3-small` 是 1536 维；切换后必须重建索引：

```bash
curl -X POST --max-time 900 http://127.0.0.1:6300/api/index
```

重建会把全部文档重新切块并重新向量化，旧向量索引会被覆盖。

## PostgreSQL

Compose 自带 `postgres:16-alpine`，每个 workspace 一个库：

```env
DATABASE_URL_TEMPLATE=postgresql+psycopg2://softwiki:<password>@postgres:5432/softwiki_{workspace}
```

`POSTGRES_PASSWORD` 放在 `~/softwiki-ci/.env`（Compose 插值用），与模板密码一致。当前库：`softwiki_kb_alpha`。

一次性迁移：

```bash
PW=$(grep '^POSTGRES_PASSWORD=' ~/softwiki-ci/.env | cut -d= -f2)
docker exec -e WORKSPACE_DIR=/data/workspace/kb-alpha softwiki-api-1 \
  python scripts/migrate_sqlite_to_postgres.py \
  --source /data/workspace/kb-alpha/.softwiki/processed.db \
  --target "postgresql+psycopg2://softwiki:${PW}@postgres:5432/softwiki_kb_alpha" \
  --replace
```

注意：`claims.id` 是字符串主键，迁移脚本只重置整型序列。

## 数据与密钥

- `workspace/` 用 bind mount，**不要** `docker compose down -v`。
- `.env` 只放在宿主；不要 `COPY` 进镜像，也不要提交。
- 备份：`tar` 打包 `workspace/` 与 `.env`；Postgres 另用 `pg_dump`：
  ```bash
  docker exec softwiki-postgres-1 pg_dump -U softwiki softwiki_kb_alpha | gzip > softwiki_kb_alpha.sql.gz
  ```
- 恢复：停栈后恢复 `workspace/`，再把 SQL dump 导入 Postgres。

## 认证（可选）

默认关闭。开启前先准备 secret 和管理员：

```env
SOFTWIKI_AUTH_ENABLED=1
SOFTWIKI_SECRET_KEY=<random-long-string>
```

```bash
docker exec -it -e WORKSPACE_DIR=/data/workspace/kb-alpha softwiki-api-1 \
  python scripts/create_admin.py --username admin --workspace kb-alpha
```

登录后使用 cookie 或 Bearer token：

```bash
curl -c cookies.txt -X POST http://127.0.0.1:6200/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"..."}'
curl -b cookies.txt http://127.0.0.1:6200/api/me
```

WebUI 目前没有登录页；开启认证后 UI 会收到 401。试用阶段建议保持关闭。

## 备份 / 恢复

```bash
scripts/backup.sh /opt/aitools/apps/softwiki/backups
scripts/restore.sh /opt/aitools/apps/softwiki/backups/softwiki-kb-alpha-YYYYmmdd-HHMMSS.tar.gz
```

归档只包含 workspace；`.env` 单独备份，绝不进归档。

## 注意事项

- 当前镜像只安装基础依赖，**不含 LightRAG**；`graph` 模块会回退到 SQL。需要 LightRAG 时在 `pyproject.toml` 的 `[graph]` extra 里安装并重建。
- `api` 与 `mcp` 是两个容器，各自持有 `WORKSPACE_DIR`；用 API 切库不会同步到 MCP（与旧 systemd 行为一致）。
- SQLite 只适合单用户/小规模；多用户试用前应切 PostgreSQL（T12 后续项）。
- 端口 `6100/6108/6200` 被旧 systemd 占用，切流前不要改默认端口。


---

## Host Agent Web（L1，opencode）

浏览器 Agent 目前仍跑在宿主机（不是容器），与 Docker 栈并行：

- systemd：`softwiki-agent-web.service`
- 端口：`6111`
- 工作区：`/opt/aitools/apps/softwiki/workspace/kb-alpha`
- 配置：`/home/operator/softwiki-ci/.softwiki_runtime/kb_alpha_*/opencode/opencode.json`
- 模型：`SHELL_MODEL=gpt-4.1-mini`（`.env`）
- 启动：`sudo systemctl start softwiki-agent-web`
- 重启：`sudo systemctl restart softwiki-agent-web`
- 日志：`journalctl -u softwiki-agent-web -f`
- 健康：`curl http://127.0.0.1:6111/`、`curl http://127.0.0.1:6200/api/agent/status`

单元文件模板：`deploy/softwiki-agent-web.service`。安装：

```bash
sudo cp deploy/softwiki-agent-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now softwiki-agent-web
```

注意：

- L1 调用**系统 opencode**（build-host 当前 `1.18.35`），不是产品化容器；升级/打包见 `docs/05-roadmap/agent-web-plan.md`。
- Agent 通过 remote MCP `http://127.0.0.1:6100/mcp` 访问 Docker 里的 SoftWiki MCP，不需要宿主 psycopg2/数据库连通性。
- `wiki-research` 权限在 opencode 层 deny `bash`/`edit` 和 `softwiki_ingest`/`index`/`rebuild_index`/`wiki_build`；remote MCP 本身仍暴露写工具，产品化需只读 sidecar。

---

## 手动部署（不 push，2026-11-24）

CI 定时器只认 `origin/master`；本地分支未 push 时，需要手动同步到 build-host。
注意 **build-host 的 CI 目录是 `/home/faye/softwiki-ci`**（不是 `/opt/aitools/apps/softwiki`，
后者只是 workspace + 备份存放处）。CI 每 3 分钟 `fetch` 一次，`origin/master` 变化时
会执行 `git reset --hard`——**手动同步的改动会在下次 CI 部署时被覆盖**，要么尽快收敛
回 origin，要么临时 `sudo systemctl stop softwiki-deploy.timer`。

```bash
# 1. 开发机：只同步代码，不动 workspace / .env
rsync -az --exclude '__pycache__' --exclude '*.pyc' \
  softwiki scripts web Dockerfile pyproject.toml kb-templates \
  faye@10.3.9.29:/home/faye/softwiki-ci/

# 2. build-host：按 CI 的 env 构建 + 起栈（project 必须叫 softwiki）
cd /home/faye/softwiki-ci
TAG=<本地 commit 短 sha> sudo -E docker compose build api web
sudo -E env TAG=<sha> \
  SOFTWIKI_ENV_FILE=/opt/aitools/apps/softwiki/.env \
  SOFTWIKI_WORKSPACE=/opt/aitools/apps/softwiki/workspace \
  SOFTWIKI_ACTIVE_WORKSPACE=armkb \
  API_HOST_PORT=6200 MCP_HOST_PORT=6100 WEB_HOST_PORT=6108 \
  SOFTWIKI_STACK_ROOT=/opt/aitools/apps/softwiki/workspace/stacks/javis \
  SOFTWIKI_SHARED_CONFIG=/opt/aitools/apps/softwiki/workspace/config \
  SOFTWIKI_AUDIT_DIR=/opt/aitools/apps/softwiki/workspace/.softwiki-audit \
  WIKIWEB_DIR=/opt/aitools/apps/softwiki/workspace/stacks/javis/armkb/exports/wikiweb \
  WIKIWEB_ENTRY=armkb/index.html \
  docker compose -f docker-compose.yml --project-name softwiki up -d --no-build
```

**踩坑**

- 直接 `docker compose up` 会用目录名当 project（`softwiki-ci`），起出**第二套栈**并占用
  6300/6301/6308；必须显式 `--project-name softwiki` 并传上面那组 env，否则挂载和库都错。
- 只重建 api 时 web 镜像不会跟着打新 tag；用 `docker tag softwiki-web:<旧> softwiki-web:<新>`。
- LLM 走 trial 网关：**实例默认**（`.env`）即为 `oneroute` + `deepseek-v4.1-flash`
  （`OPENAI_API_BASE` / `OPENAI_API_KEY` / `EXTRACTION_MODEL` / `ANALYSIS_MODEL` / `WIKI_MODEL`），
  key 由 `DEEPSEEK_API_KEY` 提供；`armkb/config/model_profiles.yaml` 也指向同一网关（不落 key）。
  embedding 仍走 OpenAI（`EMBEDDING_API_KEY` 独立）。**助手（opencode）的 shell 模型**
  2026-11-26 起也切到 trial 网关：`SHELL_API_BASE/SHELL_API_KEY/SHELL_MODEL`
  = oneroute / `DEEPSEEK_API_KEY` / `deepseek-v4.1-flash`（与 trial 的 SWAgent 一致）。
  2026-11-26 之前默认是 Gemini，预付额度耗尽后切到 trial 网关。

**回滚**：`sudo docker tag softwiki-api:<旧sha> softwiki-api:latest` 相当于回退 TAG；
数据库备份 `backup-armkb-<ts>.sql.gz`，workspace 备份 `backup-armkb-ws-<ts>.tgz`。

### armkb Graph v2 重建记录（2026-11-24）

- 备份：`backup-armkb-20261124-033106.sql.gz`（25MB）、`backup-armkb-ws-20261124-033106.tgz`（330MB）、
  镜像 `softwiki-api:pre-graphv2-20261124-033106`。
- LLM：armkb `config/model_profiles.yaml` 切到 trial 的 oneroute `deepseek-v4.1-flash`；
  key 放在 build-host `/opt/aitools/apps/softwiki/.env` 的 `DEEPSEEK_API_KEY`。
- 重抽：`scripts/graph_reextract.py --workers 3 --windows 6`；实际按 1–38 / 39–47 / 48–73
  分三段并行完成，随后 `--canonical-only --normalize`。
- 数据：claims **15,465**、canonical **14,704**、entities **9,256**（合并 634 / 别名 2,244）、
  relationships **9,491**（8,957 挂 claim，`graph_topup --all` 补 504 后）、events **743**。
- 投影：`knowledge_v2_projections.py` + `graph_normalize.py` 重跑。
- 演示：`/graph-studio`（6108）；API `/api/graph/{search,entity,path}`。镜像：api `c8a673e`、web `fitv1`。
- 别名治理：`armkb/config/entity_aliases.yaml`（Helium↔MVE、AMBA AXI↔AXI 等），
  `scripts/graph_normalize.py` 合并并把边端点改写为 canonical 名称。
- wiki：旧 929 页归档到 `exports/wiki/pages.pre-graphv2-20261124-052035`；
  重建 233 个页面文件（含拆页），重点实体（Cortex-M55/M85/M7、Ethos-U55、PL031、
  NIC-400、Helium、AMBA AXI）已确认有 wiki。
- 验收：24 题实体命中 100%，术语覆盖 82.0% vs 40.3%，p50 62ms / p95 79ms
  （`scripts/graph_acceptance.py --runs 5`）。
- 504 补图：`graph_topup.py --all`（73 篇、只跑图）把关系 4,572 → **9,491**；
  之后重跑 `graph_normalize.py` + `knowledge_v2_projections.py`（8,957 挂 claim）。
- 性能：`link_entities` 的子串前置 + 正则缓存把检索 p50 从 502ms 降到 **62ms**。
