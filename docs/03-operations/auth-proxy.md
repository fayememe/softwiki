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
