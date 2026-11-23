# 用户系统使用手册（三种模式）

> 状态：✅ 2026-11-22
> 关联：[auth-oidc.md](../02-design/auth-oidc.md)、[auth-proxy.md](./auth-proxy.md)

**安装方式完全相同**：同一套镜像、同一个 compose、同一份配置结构。
唯一的区别是一个配置项：

```ini
SOFTWIKI_AUTH_MODE=off | local | oidc | proxy
```

| 模式 | 你说的情况 | 谁是谁 | 需要登录吗 |
|---|---|---|---|
| `off` | 单机版 | 打开的人就是本机管理员 | 不需要 |
| `proxy` | 用户版（接客户/学校 ID） | 反代注入身份 | 需要 |
| `proxy` + Authelia | demo 用户版（示例） | 示例自带两个账号 | 需要 |
| `local` / `oidc` | 早期路径，保留兼容 | 见文末 | 需要 |

---

## 一、单机版（`off`）

### 行为

```ini
SOFTWIKI_AUTH_MODE=off      # 默认值，不填就是这个
```

- **打开即用，你就是管理员**：每个请求都被当作本机超级用户，角色 `wiki-admin`。
- 不会创建任何账号（Users 面板里只有一条 `local:machine:superuser`，不可登录）。
- 侧栏显示 `Admin · all` 是正常的——那是"当前角色 + 可见全部库"，不是某个账号。

### 适合

- 单机部署、自己用、演示、还没有身份系统的阶段。
- **不适合**：任何能连到公网的实例。等价于"谁打开端口谁是管理员"。

### 怎么确认自己处于单机版

```bash
curl http://<host>:6200/api/auth/providers
# {"mode":"off", ...}
```

### 什么时候该切走

只要有人除了你以外能访问，就该切到用户版。切换只需改 `SOFTWIKI_AUTH_MODE`（见第三节）。

---

## 二、用户版（`proxy` + 外部身份系统）

### 2.1 初始化管理员（**安装时必须做**）

这是最容易漏的一步：一开始没有任何人拥有管理员角色，而"批准用户 / 改角色"本身需要管理员。

三种做法，任选其一：

**A. 安装时给内置 admin 设密码（推荐）**

```ini
# 首次启动前写进 .env。只在"没有 admin 账号"时生效，之后不会覆盖。
SOFTWIKI_ADMIN_PASSWORD=<自己设，至少 12 位>
```

首次启动后用它登录，再去做组映射 / 批准用户。

**B. 不设密码 → 自动生成**

首次启动日志会打印一次（只打印一次，记下来）：

```text
====================================================================
  Built-in admin created. Username: admin
  Password: 1YMeSBexVLiewIpx7-5PyQzI
  This is shown once. Change it with scripts/set_admin_password.py
====================================================================
```

**C. 事后找回 / 重置**

```bash
python3 scripts/set_admin_password.py            # 交互输入
# 或在容器里：
docker exec -it <api-container> python3 scripts/set_admin_password.py
```

> 内置账号：用户名固定 `admin`，角色固定 `wiki-admin`，只存 scrypt 哈希。
> 它是一个**应急入口**，不是用户系统——其他账号一律来自外部身份源。

### 2.2 建组与映射

外部系统给"组"，softwiki 把组映射成角色。四个角色：

| 角色 | 能做什么 |
|---|---|
| `wiki-study` | 只读：搜索、问答、看 wiki |
| `wiki-work` | 只读 + 生成/提交 wiki 草稿 |
| `wiki-manage` | 写库：ingest、重建索引、删文档、裁决冲突、建库 |
| `wiki-admin` | 全部，含用户管理与权限策略 |

```yaml
# <workspaces_root>/config/identity.yaml
groups:
  staff:
    - wiki-work
  faculty:
    - wiki-manage
  it-ops:
    - wiki-admin
```

- 角色**每次请求重算**：改完映射不用重启，也不用让用户重新登录。
- 没映射的组 → 角色回落 `wiki-study`，且默认 `pending`。
- 命令行验收：`python3 scripts/verify_proxy_headers.py https://<softwiki>/ --user alice --groups staff`

### 2.3 首次登录的三种结果

| 情况 | 结果 | 处理 |
|---|---|---|
| 组已映射 | 直接可用，角色 = 映射结果 | 无需操作 |
| 组未映射 | `pending=true`，只能看只读页 | 管理员在 **Users** 面板批准，或加映射 |
| 账号被停用 | 拒绝 | 管理员重新启用 |

`SOFTWIKI_UNKNOWN_USER_POLICY` 控制未知用户的默认策略（默认 `pending`）。

### 2.4 管理员日常

- **批准用户**：侧栏 Admin → Users，pending 行点 Approve
- **改角色**：同一面板的 Role 下拉（覆盖映射）
- **限定可见库**：`kb_scope`（默认 `*` = 全部；填具体库名则只听那些）
- **审计**：Admin → Audit log，记录真实生效角色与来源 IP

### 2.5 已知边界

- 反代必须**覆盖**客户端自带的 `X-Auth-Request-*`，否则可被伪造
  （`auth-proxy.md` 第 6 节有清单）
- softwiki 端口必须只对反代开放
- 反代要放行 `/api/auth/password|me|providers`，否则身份系统故障时无法登录
- 限速是**按进程**的；多 worker 部署时实际上限会乘以 worker 数

---

## 三、demo 用户版（示例：Authelia）

目的是"十分钟看到效果"，不是生产蓝图。

### 3.1 启动

```bash
cd deploy/auth-demo
./setup.sh
```

远程机器（如 118）：

```bash
DEMO_PUBLIC_HOST=<公网IP> DEMO_BIND_ADDR=0.0.0.0 ./setup.sh
```

### 3.2 访问与账号

| 地址 | 用途 |
|---|---|
| `https://<host>:6190` | 完整 WebUI（经反代，已带身份） |
| `https://<host>:6191` | Authelia 登录页 |

| 账号 | 密码 | 组 | 角色 |
|---|---|---|---|
| `alice` | `demo123` | staff | `wiki-work` |
| `bob` | `demo123` | student | `wiki-study` |
| `admin` | `demo123` | ops | `wiki-admin` |

### 3.3 想看的三种效果

1. **组映射**：alice 能写 wiki 草稿，bob 只能看。
2. **待放行**：新建一个 Authelia 用户，组填 `visitors`（未映射），登录后是 `pending`，
   在 Users 面板批准。
3. **权限差异**：admin 侧栏有 ADMIN（New KB），alice 有 CONTRIBUTOR（Ingest/Conflicts），
   bob 只有 KNOWLEDGE。刷新即按角色重算。
4. **应急入口**：`docker stop auth-demo-authelia-1` 后，
   仍可用内置账号 `POST /api/auth/password` 登录（admin / 启动日志里的随机串）。

### 3.4 改演示账号 / 角色

```bash
# 角色：改映射即可，刷新生效
vi deploy/auth-demo/workspaces/config/identity.yaml

# 账号：改 Authelia 用户文件后重启
vi deploy/auth-demo/authelia/users.yml
docker compose restart authelia
```

---

## 四、三种模式的对照表

| | 单机版 `off` | 用户版 `proxy` | demo `proxy`+Authelia |
|---|---|---|---|
| 需要 IdP | 否 | 是 | 示例自带 |
| 需要登录 | 否 | 是 | 是 |
| 管理员来源 | 本机即管理员 | 内置 `admin` + 组映射 | 内置 `admin` + 映射 |
| 用户来源 | 无账号 | 外部 IdP | Authelia YAML |
| 首次安装步骤 | 无 | 设 `SOFTWIKI_ADMIN_PASSWORD` | `./setup.sh` |
| 公网可用 | ❌ 绝对不要 | ✅（需收口端口） | ⚠️ 仅演示 |
| 适合 | 自己用 | 交付客户 | 演示 |

---

## 五、`local` / `oidc` 模式（保留兼容）

早期路径：身份由 adapter 从 `claims`（OIDC）或本地用户表获得。

- `POST /api/auth/login` 传 `{"provider":"oidc","claims":{...}}`
- **不校验 claims 来源**，只适合放在可信反代之后，或由自有 BFF 调用
- 新部署请直接用 `proxy`：协议交给反代，softwiki 只读 header

需要标准 OIDC 授权码流程（应用内完成 code 交换 + JWKS 验签）时，目前**没有实现**；
推荐用反代完成（见 [auth-proxy.md](./auth-proxy.md)）。

---

## 六、排错

| 现象 | 原因 | 处理 |
|---|---|---|
| 打开就是管理员，没有登录页 | 处于 `off` 模式 | 设 `SOFTWIKI_AUTH_MODE=proxy` |
| 登录后仍是 `pending` | 组未映射 / 用户未批准 | 加映射或 Users 面板批准 |
| 登录后角色是 `wiki-study` | 组名与 `identity.yaml` 不一致 | 核对大小写与拼写 |
| 忘记 admin 密码 | — | `scripts/set_admin_password.py` |
| 反代后所有人共用一个限速额度 | 反代没传 `X-Forwarded-For` | 反代加 `proxy_set_header X-Forwarded-For $remote_addr` |
| 身份系统挂了进不去 | 反代没放行登录路径 | 放行 `/api/auth/password` |
| `identity` 显示 `proxy:xxx:alice` 但角色不对 | 映射文件不是 `identity.yaml` | 确认没写到 `users.yaml` |

> 审计里有两类记录：`auth.password` 记的是**真实客户端地址**（反代受信时取
> `X-Forwarded-For` 第一跳）；通用的 `POST /api/...` 请求记录仍记 TCP 对端
> （反代场景下是反代地址）。排障时以 `auth.*` 记录为准。
