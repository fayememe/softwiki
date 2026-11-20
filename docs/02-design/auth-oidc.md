# 身份接入与权限控制（OIDC / 微信 / 超级用户）

> status: 🚧 讨论中（2026-11-19，待评审）
> 定位：**我们不做用户系统，只做「可接入」**。身份由客户/学校/第三方提供，我们负责把外部身份映射成本地权限。
> 本文取代 `roles-permissions.md` §6「安全边界」的旧描述（当前为客户端自报角色、可伪造）。
>
> **2026-11-19：主体设计已实现**，见 §12。剩余未决见 §11。

## 0. 一句话设计

```
外部身份源（OIDC / 微信 / 客户自有）
   → 统一转成 (issuer, subject, 属性)      ← 接入层，可插拔
   → 本地用户表 + 组映射 + 覆盖            ← 授权层，我们说了算
   → 角色 + kb_scope                       ← 由本地计算
   → capability 检查 + 审计日志
```

**核心判断**：认证（Authentication）交给外部，授权（Authorization）留在本地。
不把角色直接写进 token，因为外部改组、改结构时不应该影响我们的权限。

## 1. 身份源抽象（「见招拆招」的落点）

不管客户用什么样的用户系统，落到我们这里只有一件事：**告诉我们「这个人是谁」**。
内部只认一个格式：

| 字段 | 必填 | 说明 |
|---|---|---|
| `issuer` | 是 | 身份源标识，如 `oidc:school`、`wechat:site` |
| `subject` | 是 | 该源内稳定唯一的用户 ID |
| `email` | 否 | 展示/联系用，**不做主键**（邮箱会变） |
| `display_name` | 否 | 展示用 |
| `groups` | 否 | 外部组列表；没有就为空，用户落 `pending` |
| `attributes` | 否 | 其它属性，先透传存起来 |

**`subject` 必须与 `issuer` 联合唯一。** 理由：微信的 `openid` 在不同应用下不同，只有带 `issuer` 才能区分。这个约束现在定死，以后接微信不会撞主键。

### 1.1 提供方注册表

```yaml
providers:
  - id: oidc:school
    adapter: oidc            # 标准 OIDC，配置即可，无需写代码
    issuer_url: https://sso.example.edu
    client_id: softwiki
    client_secret_ref: env:OIDC_SCHOOL_SECRET
    scopes: [openid, profile, email, groups]
  - id: wechat:site
    adapter: wechat          # 微信开放平台网站应用扫码
    app_id: wx...
    app_secret_ref: env:WECHAT_SITE_SECRET
```

- **标准 OIDC 类**：现成 adapter，只做配置。
- **非标准类（微信）**：单独 adapter，把 `code → access_token → userinfo` 转成上面的统一格式。
- 客户指定新系统时，再写一个 adapter 并注册一条记录。**映射层、用户表、审计、降级模式都不用改。**

### 1.2 现在要做的两个

按 operator 指示：**先做 OIDC 和微信两个**，其余按客户指定再加。

## 2. 本地用户表

```
users
  id              PK
  issuer          TEXT   ┐
  subject         TEXT   ┘ 联合唯一
  email           TEXT   可空
  display_name    TEXT   可空
  groups          JSON   外部组快照（最近一次登录）
  kb_scope        TEXT   检索范围，见 §3
  role_override   TEXT   可空；显式覆盖计算结果
  is_active       BOOLEAN 本地禁用开关
  created_at / last_login_at
```

**规则**：

- 首次登录自动 insert 一行；之后每次登录更新 `email` / `display_name` / `groups` / `last_login_at`。
- **角色每次请求时计算**，不在登录时固化。否则管理员改了映射表，要等用户重新登录才生效。
- `is_active = false` **优先级最高**：外部说他是管理员也不管用。本地必须能拒绝外部授予。

## 3. `kb_scope`

- 值形态：`"*"` 或库名数组（如 `["coffee-kb", "ai-history-kb"]`）。
- **默认 `"*"`**。
- **`"*"` 是通配符**：永远代表「当前所有库」，新库自动可见。限缩到某几个库是显式的管理动作。
- **typo 不阻断**：写错库名就是不 match，不报错、不校验。但管理页显示「该用户实际可见 0 个库」，避免静默变成看不见任何库。

## 4. 组映射与三态

```
映射表：external_group → softwiki_role
```

- 一个用户命中多个组时**取最高等级**；不合适就用 `role_override` 压下来。
- 不在任何组里：按 `unknown_user_policy` 三态，**默认 `pending`**。

| 三态 | 行为 |
|---|---|
| `deny` | 拒绝登录 |
| `lowest` | 登录，给 `wiki-study` 只读 |
| `pending` | 登录，但什么都做不了，等管理员放行 |

> **`pending` 的配套要求**：必须有管理员放行入口（管理页/接口列出待审用户并授角色），否则用户会被卡死。

## 5. 超级用户

**定义**：不是登录表里的账号，而是「没有身份系统的运行模式」下的万能身份。
**关键不在于有没有，而在于怎么限制。**

| 限制 | 设计 |
|---|---|
| **默认状态** | **关闭**。需要显式开启 |
| **网络位置** | **仅本机**。应用层只看连接远端地址（`request.client.host`），**不信任 `X-Forwarded-For`** |
| **凭据** | 开启时附带 token（`.env`，不入库、不入仓库） |
| **TTL** | 本机开启可手动关闭；**远程开启强制 TTL**，到点自动失效 |
| **敏感操作** | 执行前**重新认证**（单机模式=输入超级用户 token；OIDC 模式=再次走认证/二次验证），并强制写审计 |
| **降级工作** | 允许。超级用户可用低等级模式工作（防止误操作） |
| **冒充他人** | **不做**。只提供只读「预览某用户视角」 |

### 5.1 部署与应用的责任切分

- **应用**：只定义「是否本机」的语义（连接远端地址）。
- **部署**：决定「本机」怎么实现（host 网络 / 端口只绑定 `127.0.0.1` / 反代只暴露指定路由）。
- 容器内看到的是 `172.x` 时，「仅本机」自然不成立——这是部署要解决的问题，应用不做特判。

> ⚠ **当前风险**：trial-host 现在是 `off` 模式且公网可达，等价于「任何人都能拿到超级用户」。
> 认证上线前**至少要先锁端口访问控制**。这件事优先级高于所有新功能。

## 6. 知识库「卸载」（脱钩，不是删除）

| 操作 | 性质 | 限制 |
|---|---|---|
| 内容编辑：删文档 / chunk / claim | 日常内容操作 | **不限** |
| **卸载知识库**：从 softwiki 移除该库的注册 | 系统级脱钩 | **受限**（敏感操作） |
| 删除数据库 / 磁盘文件 | 不属于 softwiki 的动作 | **不做**，由运维在系统外处理 |

**脱钩语义**：数据库、原始文件、配置文件**全部保留**，只是 softwiki 不再承认它存在。今后可重新注册，内容就能回来。

需要同时处理：

- `META` / `scope.md` / `topics.yaml`：**保留**（便于重新注册）；
- MCP 路由与 Web 入口：**隐藏**；
- 向量索引与 claim 缓存：**可清空**（重新注册时重建）；
- 是否留一条「已卸载」历史记录：**保留**，否则以后查不到它曾经存在。

> 前置条件：数据库必须有备份，「脱钩可恢复」才真正成立。
> 已知缺口：`progress.md` 记录 **Postgres 备份尚未并入 `scripts/backup.sh`**。

## 7. 审计日志

**记**：

- 写操作：入库、抽取、索引、修改、**卸载库**、权限/映射改动、冲突裁定、Wiki 生成；
- 敏感操作：所有超级用户操作（**成败都记**，以及敏感的失败尝试）；
- 身份事件：登录、登出、角色变更、降权与恢复、token 签发与作废。

**不记**：只读查询。但保留**聚合计数**（回答「这个库有没有人用」）。

**每条至少含**：时间、模式（单机 / OIDC）、身份（用户 ID 或「超级用户」）、来源 IP、操作名、目标（库/文档/claim）、结果、原因或备注。

**定位**：审计日志是**系统日志**，**不随内容删除一起被删**。否则删掉文档后审计记录也消失，日志就废了。

### 7.1 实现

- `softwiki/audit.py`，append-only JSON Lines；
- 位置 `<workspaces root>/.softwiki-audit/audit.log`，可用 `SOFTWIKI_AUDIT_LOG` 覆盖；
- API：`role_middleware` 统一记录所有非 GET/HEAD/OPTIONS 请求（异常也记 `result=error`）；
- MCP：`ingest` / `index` / `wiki_build` / `workspace_set` / `modules_set` 显式记录；
- 写失败只记 error log，不影响被审计的操作本身；
- 读取：`GET /api/admin/audit`（管理面）。

## 8. 降级工作模式（原则）

> **高等级用户可以使用低等级权限模式工作。**

- **固有角色**：来自本地用户表（映射 + override）的结果。
- **有效角色** = `min(固有角色, 会话请求降级角色)`（按角色等级排序）。
- **只能降不能升**：低等级用户不能自升。
- **只做自我降级**，不做 impersonation（见 §5）。
- 单机模式下同样适用：没有身份，也可以「以 `wiki-study` 只读操作」，这是防误操作手段，和身份无关。

## 9. 与现有代码的距离（现状核查）

> **2026-11-19 更新：本节列出的缺陷已全部修复**，详见 §12 实现状态。
> 保留原文作为改动前的证据。

| 现状 | 位置 | 影响 |
|---|---|---|
| 角色优先级：header > cookie > env > 默认 `wiki-admin` | `softwiki/api/server.py:106-122` | **默认是最高权限**，必须改成 fail-closed |
| `normalize_role()` 未知角色回退到 `wiki-admin` | `softwiki/permissions.py:55-60` | 拼错角色名 = 拿到管理员，必须改成回退 `wiki-study` |
| `_load_policy()` 吞掉异常返回默认 | `softwiki/permissions.py:82-83` | 空 `except`，违反 `AGENTS.md` §5.1 |
| 已有 `auth_middleware`（`SOFTWIKI_AUTH_ENABLED`） | `api/server.py:125-161` | 旧用户系统骨架，demo 阶段关闭；需决定复用还是替换 |
| `WorkspaceMember` 表 | `api/server.py:151-156` | 已有的库级成员关系，可与 `kb_scope` 对齐 |
| KB 发现靠目录扫描 | `softwiki/kb/registry.py:213-225` | 「卸载」= 改注册状态，不能再靠目录存在与否判断 |

## 10. 决策记录

| # | 决策 | 日期 |
|---|---|---|
| D1 | 认证归外部、授权归本地；角色不写进 token | 2026-11-19 |
| D2 | `(issuer, subject)` 联合唯一，为微信预留 | 2026-11-19 |
| D3 | `kb_scope` 默认 `"*"`，`"*"` 为通配符（新库自动可见） | 2026-11-19 |
| D4 | `kb_scope` typo 不阻断，管理页提示可见 0 库 | 2026-11-19 |
| D5 | 不在组里默认 `pending`，配管理员放行入口 | 2026-11-19 |
| D6 | 超级用户始终存在、默认关闭、仅本机、不信任 `X-Forwarded-For` | 2026-11-19 |
| D7 | 敏感操作需重新认证 + 强制审计 | 2026-11-19 |
| D8 | 卸载库 = 脱钩，数据库/文件/配置保留 | 2026-11-19 |
| D9 | 审计记写操作与敏感操作，只读不记（留聚合计数） | 2026-11-19 |
| D10 | 降级模式 `min(固有, 会话)`，只降不升，不冒充 | 2026-11-19 |
| D11 | 先做 OIDC + 微信两个 adapter，其余按客户指定 | 2026-11-19 |
| D12 | 应用定「本机」语义，部署定网络实现 | 2026-11-19 |

## 11. 未决

- [ ] 微信登录定位：面向公众/校外入口，还是校内便利登录？（微信不提供组信息，权限只能人工绑定）
- [ ] 旧 `auth_middleware` + `User/WorkspaceMember` 是复用还是替换（当前保留，`SOFTWIKI_AUTH_ENABLED` 仍可启用）
- [ ] 多进程部署时超级用户会话与二次认证状态只在单进程内存中，需外部存储
- [x] **proxy 模式**：信任反代注入的身份 header（`SOFTWIKI_AUTH_MODE=proxy`），
      协议由 oauth2-proxy / Authelia / Authentik 完成；
      信任边界在代码里强制（只认 `SOFTWIKI_TRUSTED_PROXIES` 内的来源，不看 `X-Forwarded-For`）。
      运维文档：[../03-operations/auth-proxy.md](../03-operations/auth-proxy.md)
- [x] 来源地址白名单 `SOFTWIKI_ALLOWED_CIDRS`（`softwiki/netacl.py`，默认关闭，配置错误时拒绝所有人）
- [ ] OIDC 的 code 交换（标准授权码流程）仍未在应用内实现；`claims` 路径可用，
      但要接真实 IdP 应走 proxy 模式（见上）

## 12. 实现状态（2026-11-19）

| 模块 | 文件 | 状态 |
|---|---|---|
| 权限 fail-closed / 降级 / KB scope | `softwiki/permissions.py` | ✅ |
| 审计日志 | `softwiki/audit.py` | ✅ |
| 身份源抽象 + OIDC / 微信 adapter | `softwiki/identity/{base,oidc,wechat}.py` | ✅ |
| 超级用户窗口（仅本机、TTL、二次认证） | `softwiki/identity/superuser.py` | ✅ |
| 本地用户表 / 组映射 / 三态 | `softwiki/identity/users.py` | ✅ |
| API：`/api/auth/*`、`/api/admin/*` | `softwiki/api/server.py` | ✅ |
| 知识库注册表 + 建库向导 | `softwiki/kb/registry_state.py`、`/api/kb/*` | ✅ |
| WebUI 建库面板 | `web/components/KbWizardPanel.tsx` | ✅ |
| 图谱子图 API | `/api/graph/overview`、`/api/graph/subgraph` | ✅ |
| 图谱页重写（Canvas） | `web/components/GraphPanel.tsx` | ✅ |

环境变量：

| 变量 | 作用 |
|---|---|
| `SOFTWIKI_AUTH_MODE` | `off`（默认，单机即超级用户）/ `local` / `oidc` |
| `SOFTWIKI_SUPERUSER_TOKEN` | 开启超级用户与二次认证用的 token；不配则远程不可开启 |
| `SOFTWIKI_REAUTH_TOKEN` | 敏感操作二次认证 token，缺省回退到超级用户 token |
| `SOFTWIKI_UNKNOWN_USER_POLICY` | `pending`（默认）/ `lowest` / `deny` |
| `SOFTWIKI_AUDIT_LOG` | 审计日志路径，缺省 `<workspaces root>/.softwiki-audit/audit.log` |
| `SOFTWIKI_DOWNGRADE_ROLE` | 进程级降级（请求级用 `X-SoftWiki-Downgrade` 或 cookie） |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | 微信 adapter 凭据 |

测试：`tests/test_identity.py`（37）、`tests/test_kb_wizard.py`（22）、`tests/test_graph_api.py`（5）；
全量 `pytest tests -q` → **175 passed**。
