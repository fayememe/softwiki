# 轻量认证示例：Authelia + nginx + softwiki（proxy 模式）

一个**可直接跑**的最小示例，用来演示「外部用户系统 → 反代 → softwiki」这条链。
不是生产蓝图：生产环境把 Authelia 换成客户自己的 IdP 即可。

```
浏览器 ──► nginx:6190 ──[auth_request]──► Authelia:9091（YAML 用户）
                │                              │
                │◄── Remote-User/Groups ───────┘
                └──► softwiki:6200（只读 X-Auth-Request-*，且只信本网段）
```

## 为什么选 Authelia

| | |
|---|---|
| 容器数 | 1（nginx 之外），无数据库 |
| 用户来源 | 一个 YAML 文件 |
| 依赖 | 无（不需要 Postgres/Redis） |
| 协议 | 自带 forward-auth；也能当 OIDC provider |

## 启动

```bash
cd deploy/auth-demo
./setup.sh
```

首次运行会：

1. 生成 Authelia 的 jwt/session/storage 密钥（本机，不入库）
2. 生成两个演示用户（`demo123`）：
   - `alice` / `staff` → `wiki-work`
   - `bob` / `student` → `wiki-study`
3. 生成自签证书（Authelia 4.38 强制 https）
4. 建一个空的演示知识库 + 组→角色映射
5. `docker compose up -d`

访问：

| 地址 | 说明 |
|---|---|
| `https://127.0.0.1:6190` | 应用（自签证书，浏览器会警告） |
| `https://127.0.0.1:6191` | 登录页 |

只有 nginx 发布端口，且绑在 `127.0.0.1`；其他机器访问请用 SSH 隧道：

```bash
ssh -L 6190:127.0.0.1:6190 -L 6191:127.0.0.1:6191 <user>@<host>
```

## 验证

```bash
# 应用层：身份是否真的到达 softwiki
../../venv/bin/python ../../scripts/verify_proxy_headers.py \
  https://127.0.0.1:6190 --insecure --user alice

# 反代链路：组 → 角色映射
docker exec auth-demo-nginx-1 sh -c \
  "wget -qO- --header='X-Auth-Request-User: alice' \
             --header='X-Auth-Request-Groups: staff' \
   http://softwiki:6200/api/auth/me"
```

预期：

```text
alice + staff    -> granted_role=wiki-work,  pending=false
bob   + student  -> granted_role=wiki-study, pending=false
stranger + visitors（未映射）-> wiki-study, pending=true   ← 默认待放行
```

浏览器实测（headless Chrome）：未登录跳 6191、登录后回到应用、
`/api/auth/me` 返回 `identity=proxy:demo:alice`、`role=wiki-work`、无 page error。

## 安全要点（示例里已经做对的部分）

1. **只有 nginx 对外**，API 与 Authelia 仅在内网。
2. nginx 用 `auth_request` 校验每个请求，**不转发**客户端自带的
   `X-Auth-Request-*`（显式置空 + 重新写入）。
3. softwiki 只信任 `172.31.240.0/24`（本示例网络）。
   从外部直连并伪造 header → `authenticated=false`。
4. 组 → 角色在 `workspaces/config/identity.yaml`，未知组默认 `pending`。

## 换成客户的 IdP

只改两处：

```yaml
# nginx：auth_request 指向客户的反代
# softwiki：SOFTWIKI_TRUSTED_PROXIES 改成客户反代的网段
```

用户、密码、微信、OIDC 握手都在客户那一侧，softwiki 不参与。

## 清理

```bash
docker compose down -v
```

生成的文件（已 gitignore）：`authelia/configuration.yml`、`authelia/users.yml`、
`certs/`、`workspaces/`、`authelia/db.sqlite3`。
