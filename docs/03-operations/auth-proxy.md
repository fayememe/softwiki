# 用反代接入外部用户系统（proxy 模式）

> 状态：✅ 已实现（2026-11-20）
> 关联：[auth-oidc.md](../02-design/auth-oidc.md)、[deployment-trial.md](./deployment-trial.md)

## 1. 结论先说

**softwiki 不实现 OIDC 协议**。协议由现成组件完成，softwiki 只读它注入的身份 header：

```
浏览器 ─► oauth2-proxy ─► Casdoor/Keycloak/Authelia/... ─► 回跳
               │
               └─► softwiki（X-Auth-Request-User / -Groups）
```

好处：不用自己写 `state`/`nonce`/PKCE/JWKS 验签/刷新；换 IdP 只改反代配置。
代价：**softwiki 的端口必须对内网封闭**，否则 header 可被伪造。

## 2. softwiki 侧配置

```ini
SOFTWIKI_AUTH_MODE=proxy

# 只信任来自这些地址的身份 header。空 = 不信任任何人（默认）。
# 172.16.0.0/12 覆盖 docker 网络；127.0.0.1 用于同机反代。
SOFTWIKI_TRUSTED_PROXIES=172.16.0.0/12,127.0.0.1

# header 名称（oauth2-proxy 的默认值就够用）
SOFTWIKI_PROXY_USER_HEADER=X-Auth-Request-User
SOFTWIKI_PROXY_GROUPS_HEADER=X-Auth-Request-Groups
SOFTWIKI_PROXY_EMAIL_HEADER=X-Auth-Request-Email
SOFTWIKI_PROXY_NAME_HEADER=X-Auth-Request-Preferred-Username

# 写进 user 表 / 审计里的 issuer 标签
SOFTWIKI_PROXY_ISSUER_LABEL=campus
```

身份链路与其它模式完全一致：`(issuer, subject)` → 本地用户表 → 组映射 → 角色 +
`kb_scope` → `pending` 默认拒绝 → 审计。

**信任边界在代码里做死**：`softwiki/identity/proxy.py` 先判断 TCP 对端是否在
`SOFTWIKI_TRUSTED_PROXIES` 内，不在就直接返回「未认证」。它**不看
`X-Forwarded-For`**（那是客户端可控的）。所以即使反代配置漏了，直连也伪造不了身份。

## 3. 演示栈：Casdoor + oauth2-proxy

选 Casdoor 的理由：开源、中文界面、**内置微信/QQ/GitHub 等第三方登录**、
自带 OIDC discovery，适合 demo 阶段"挂上 softwiki"。

```bash
# 1) 起用户系统 + 反代（配合主 compose 使用）
docker compose -f docker-compose.yml -f docker-compose.auth-demo.yml up -d casdoor oauth2-proxy

# 2) Casdoor 初始化：浏览器打开 http://<host>:8000 ，默认 admin/123
#    - Providers → 添加 WeChat，填 AppID/AppSecret，设置回调域名
#    - Applications → 新建应用 softwiki
#        Redirect URLs: http://<host>:6180/oauth2/callback
#        记录 Client ID / Client Secret
#    - 在应用里勾选可选用的 Provider（例如 WeChat）

# 3) 把 Client ID/Secret 写进 .env
#    OIDC_CLIENT_ID=...
#    OIDC_CLIENT_SECRET=...
#    OAUTH2_PROXY_COOKIE_SECRET=$(openssl rand -base64 32 | tr -d '=' | head -c 32)
```

## 4. 端口必须这样改（关键）

proxy 模式下，**只有反代对公网暴露**，web/mcp 绑回环：

```ini
# .env
SOFTWIKI_AUTH_MODE=proxy
SOFTWIKI_TRUSTED_PROXIES=172.16.0.0/12,127.0.0.1
WEB_HOST_PORT=127.0.0.1:6108
MCP_HOST_PORT=127.0.0.1:6100
```

反代监听 `6180`（见 compose 文件）。外部只能访问 `6180`。

## 5. 验证清单

| 步骤 | 期望 |
|---|---|
| 浏览器打开 `http://<host>:6180/` | 跳 Casdoor 登录，可选择微信 |
| 登录后回到 softwiki | 页面正常，`/api/auth/me` 返回 `authenticated:true` |
| `curl http://<host>:6108/` | **连接失败或 403**（web 只绑回环） |
| 直接 `curl -H 'X-Auth-Request-User: admin' http://127.0.0.1:6108/api/auth/me` | `authenticated:false`（来源不在信任列表） |
| 在反代后面伪造 header | oauth2-proxy 覆盖为真实用户；见第 6 条 |
| 未在用户表的人首次登录 | `pending`，只能看只读页；管理员在 **Users** 面板放行 |

自动化验证脚本：

```bash
./venv/bin/python scripts/e2e_proxy_auth.py
# trusted authenticated=True forged rejected=True
```

## 6. 安全清单（上线前逐条确认）

1. **web/mcp/api 不监听公网**（`127.0.0.1:` 或内网网卡）。
2. **反代必须覆盖**客户端自带的 `X-Auth-Request-*`：
   `oauth2-proxy --set-xauthrequest` 会自行写入；若前面还有 nginx，用
   `proxy_set_header X-Auth-Request-User $sent_http_x_auth_request_user;` 并清掉入站值。
3. `SOFTWIKI_TRUSTED_PROXIES` 只填反代所在网段，不要填 `0.0.0.0/0`。
4. `SOFTWIKI_AUTH_MODE=proxy` 时不要再开 `SOFTWIKI_AUTH_ENABLED`。
5. 组映射先在 Casdoor 里分组，再在 softwiki 的 `config/users.yaml` 里映射到角色；
   不在映射里的组 → 角色回落 `wiki-study`。
6. 反代、Casdoor、softwiki 之间的 HTTP 只在容器网络内；对外用 HTTPS。
7. 审计日志里确认记录的是**真实生效角色**，不是环境变量里的默认值。

## 6.5 对接契约（交付给客户/第三方）

**我们提供接口，登录系统由对接方负责。** 边界如下：

### 对接方负责

| 项 | 说明 |
|---|---|
| 身份来源 | 自己的 IdP（学校 OIDC / 企业微信 / Casdoor / Keycloak…） |
| 登录页、账号、密码、微信等第三方绑定 | 全在对接方的系统里 |
| 合规 | 域名、ICP 备案、微信开放平台主体审核 —— **都是对接方的事** |
| 反代 | 跑 oauth2-proxy / Authelia / Authentik，把身份写进 header |
| 网络 | 让 softwiki 只被反代访问（不对外暴露 6108/6200/6100） |

### 我们负责

| 项 | 说明 |
|---|---|
| 信任这些 header | `X-Auth-Request-User`（必需）、`-Groups`、`-Email`、`-Name`（可选），名称可配 |
| 只信任指定来源 | `SOFTWIKI_TRUSTED_PROXIES`，不合规来源一律当匿名 |
| 组 → 角色映射 | `config/users.yaml`，对接方给组名，我们配角色 |
| 首次登录 | 默认 `pending`，管理员在 **Users** 面板放行 |
| 审计 | 记录真实生效角色与来源 |

### 验收（对接方跑这一条即可）

```bash
python3 scripts/verify_proxy_headers.py https://<softwiki>/ --user alice --groups staff
```

期望输出：

```text
mode: proxy
trusted peers: ['172.16.0.0/12']
identity: proxy:campus:alice  role: wiki-study  pending: True
OK  headers are honoured: the proxy identity reaches the app.
```

`pending: True` 是正常的——新用户第一次进来默认待放行。

### 必须验证的负面用例

| 场景 | 期望 |
|---|---|
| 直接访问 softwiki（绕过反代）并伪造 header | `authenticated: false` |
| 不带任何 header 访问 | `authenticated: false` |
| 未在组映射里的用户 | 角色回落 `wiki-study`，不能提权 |

实测（本机）：

```text
受信来源 + X-Auth-Request-User: alice       → authenticated: true
同一 header，来源改成非受信网段              → authenticated: false
不带 header                                 → authenticated: false
```

## 6.6 已部署的示例（trial-host）

`deploy/auth-demo/` 已部署在 trial-host，作为可点的参考实现：

| 地址 | 说明 |
|---|---|
| `https://118.193.105.3:6190` | 应用（自签证书，浏览器会警告） |
| `https://118.193.105.3:6191` | Authelia 登录页 |

账号：`alice / demo123`（staff → wiki-work）、`bob / demo123`（student → wiki-study）。

实测（2026-11-21，headless Chrome 真实登录）：

```text
alice -> identity=proxy:demo:alice  role=wiki-work   pending=false
bob   -> identity=proxy:demo:bob    role=wiki-study  pending=false
未映射组 -> role=wiki-study, pending=true
```

部署要点（踩过的坑，换环境时复用）：

1. **compose 常经 `sudo` 调用**，sudo 会清空环境变量 → 参数写进 `.env` 由 compose 读取，
   不要只靠命令行传参；
2. 没有 docker 组权限时用 `COMPOSE_CMD="sudo -n /usr/local/bin/docker-compose"`、
   `DOCKER_CMD="sudo -n docker"`；
3. Authelia 4.38 强制 https，自签证书的 SAN 要包含公网 IP；
4. 重新生成 storage 密钥时必须同时删 `db.sqlite3`，否则报
   "encryption key does not appear to be valid"；
5. 登录页的 SPA 资源是绝对路径 → 登录页必须独立端口，不能挂在 `/authelia/` 子路径；
6. `ForwardAuth` 返回 302，nginx `auth_request` 不接受 → 用 `AuthRequest`（401）+ `error_page`。

## 7. 换别的用户系统

只要它能做 forward-auth 并注入 header，就适用：

| 方案 | 说明 |
|---|---|
| **Authelia** | 自带 forward-auth；无微信，需要 OAuth2 通用 provider |
| **Authentik** | 有 forward-auth outpost；第三方登录靠 generic OAuth，微信可配 |
| **Keycloak** | 功能最全，最重；微信需要自定义 Identity Provider |
| **oauth2-proxy** | 不自带用户库，配合任一 OIDC IdP；Casdoor 组合最省事 |

softwiki 侧只改 `SOFTWIKI_PROXY_*_HEADER` 少数几个变量，代码不动。

## 8. 与 IP 白名单的关系

两者互补：

```ini
# 应用层来源白名单（可选，默认关闭；为空时不启用）
SOFTWIKI_ALLOWED_CIDRS=203.0.113.0/24
SOFTWIKI_TRUSTED_CIDRS=127.0.0.0/8,172.16.0.0/12
```

- `ALLOWED_CIDRS` 为空 → 不启用（向后兼容）；
- 配置写错 → **拒绝所有人**（fail-closed，避免手滑全开）；
- `TRUSTED_CIDRS` 默认包含回环与私有网段，因为容器健康检查和 web→api 反代都在里面。

它挡的是"谁能连进来"，不是"你是谁"；身份仍由 proxy 模式的 header 决定。
