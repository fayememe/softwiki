# javis 部署（Docker Compose + CI/CD）

> 目标：把 softwiki 以 Docker Compose 部署到 `javis`（`10.3.9.29`），由 CI 自动构建、启动、健康检查与回滚。
> 试用阶段与旧 systemd 部署**并行**：旧栈占 `6100/6108/6200`，新栈先用 `6301/6308/6300`，验收后再切。

## 拓扑

| 服务 | 容器端口 | 宿主端口（并行） | 说明 |
|---|---|---|---|
| `api` | 6200 | 6300 | FastAPI REST |
| `mcp` | 6100 | 6301 | MCP（SSE + Streamable HTTP） |
| `web` | 6108 | 6308 | Next.js，`/api` 反代到 `http://api:6200` |

- 数据：`/opt/aitools/apps/softwiki/workspace` → 容器 `/data/workspace`（SQLite 等仍在其中）。
- 密钥：`/opt/aitools/apps/softwiki/.env`（不进镜像、不进 git）。
- 当前活动库：`SOFTWIKI_ACTIVE_WORKSPACE=armkb`（API 可用 `/api/workspace` 切换；MCP 需重启容器才会跟随）。

## 前置

1. javis 已安装 Docker 26 + Compose 2.26。
2. javis 的 SSH key 已作为 **read-only deploy key** 加入 Forgejo 仓库 `faye/softwiki`。
3. `/opt/aitools/apps/softwiki/.env` 存在。

验证：

```bash
ssh faye@javis 'cd ~/mydrv/git/softwiki && git ls-remote origin HEAD'
```

## 首次部署（并行端口）

```bash
ssh faye@javis
git clone ssh://git@10.3.9.19:2222/faye/softwiki.git ~/softwiki-ci
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

## 回滚

```bash
cat ~/softwiki-ci/.deploy/last-good-sha
cd ~/softwiki-ci
TAG=<sha> docker compose --project-name softwiki up -d --no-build
```

## Embedding（OpenAI）

javis 的 `.env` 需要独立的 embedding 凭据（不要和 chat 的 Google/DeepSeek key 混用）：

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

`POSTGRES_PASSWORD` 放在 `~/softwiki-ci/.env`（Compose 插值用），与模板密码一致。当前库：`softwiki_armkb`。

一次性迁移：

```bash
PW=$(grep '^POSTGRES_PASSWORD=' ~/softwiki-ci/.env | cut -d= -f2)
docker exec -e WORKSPACE_DIR=/data/workspace/armkb softwiki-api-1 \
  python scripts/migrate_sqlite_to_postgres.py \
  --source /data/workspace/armkb/.softwiki/processed.db \
  --target "postgresql+psycopg2://softwiki:${PW}@postgres:5432/softwiki_armkb" \
  --replace
```

注意：`claims.id` 是字符串主键，迁移脚本只重置整型序列。

## 数据与密钥

- `workspace/` 用 bind mount，**不要** `docker compose down -v`。
- `.env` 只放在宿主；不要 `COPY` 进镜像，也不要提交。
- 备份：`tar` 打包 `workspace/` 与 `.env`；Postgres 另用 `pg_dump`：
  ```bash
  docker exec softwiki-postgres-1 pg_dump -U softwiki softwiki_armkb | gzip > softwiki_armkb.sql.gz
  ```
- 恢复：停栈后恢复 `workspace/`，再把 SQL dump 导入 Postgres。

## 认证（可选）

默认关闭。开启前先准备 secret 和管理员：

```env
SOFTWIKI_AUTH_ENABLED=1
SOFTWIKI_SECRET_KEY=<random-long-string>
```

```bash
docker exec -it -e WORKSPACE_DIR=/data/workspace/armkb softwiki-api-1 \
  python scripts/create_admin.py --username admin --workspace armkb
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
scripts/restore.sh /opt/aitools/apps/softwiki/backups/softwiki-armkb-YYYYmmdd-HHMMSS.tar.gz
```

归档只包含 workspace；`.env` 单独备份，绝不进归档。

## 注意事项

- 当前镜像只安装基础依赖，**不含 LightRAG**；`graph` 模块会回退到 SQL。需要 LightRAG 时在 `pyproject.toml` 的 `[graph]` extra 里安装并重建。
- `api` 与 `mcp` 是两个容器，各自持有 `WORKSPACE_DIR`；用 API 切库不会同步到 MCP（与旧 systemd 行为一致）。
- SQLite 只适合单用户/小规模；多用户试用前应切 PostgreSQL（T12 后续项）。
- 端口 `6100/6108/6200` 被旧 systemd 占用，切流前不要改默认端口。
