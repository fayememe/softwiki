# 角色与 capability mapping（team trial）

> status: 🚧 讨论中（2026-10-31）
> 目标：内部小团队试用，不做用户系统，不做 API key；角色由客户端自报。
> 这是**信任型便利控制**，不是安全边界。

## 1. 四个角色

| 角色 | 定位 |
|---|---|
| `wiki-study` | 只读研究 |
| `wiki-work` | 贡献者；team trial 可直接 ingest/index |
| `wiki-manage` | 内容管理；ingest/index/publish/adjudicate |
| `wiki-admin` | 系统管理；全部 |

团队试用为了 Hermes 直接文档输入，**把 `wiki-work` 的 `ingest.write` / `index.write` 打开**。  
如果以后恢复严格语义，从 mapping 里删掉即可。

## 2. Mapping

工作区文件：

```text
<workspace>/config/permissions.yaml
```

示例：

```yaml
version: 1
roles:
  wiki-study:
    allow:
      - read.*
  wiki-work:
    allow:
      - read.*
      - wiki.build
      - wiki.preview
      - ingest.write
      - index.write
  wiki-manage:
    allow:
      - read.*
      - wiki.build
      - wiki.preview
      - wiki.apply
      - ingest.write
      - index.write
      - document.delete
      - conflict.adjudicate
      - nli.scan
  wiki-admin:
    allow:
      - "*"
```

默认在 `softwiki/permissions.py`；没有文件时使用默认值。

## 3. 入口如何指定角色

### Web

侧栏角色选择器写 cookie：

```text
softwiki_role=wiki-study
```

API middleware 读取 cookie；刷新后生效。

### opencode / CLI

```bash
softwiki shell --mode wiki-study
softwiki shell --mode wiki-work
softwiki shell --mode wiki-manage
```

或设置：

```bash
SOFTWIKI_ROLE=wiki-work
SOFTWIKI_MODE=wiki-work
```

### MCP / Hermes

单端口：

```text
http://build.example.internal:6100/mcp
```

客户端传 header：

```http
X-SoftWiki-Role: wiki-work
```

Hermes 直接文档输入，使用 `wiki-work`（team trial mapping 已允许 ingest/index）。  
opencode 按其 session 选择角色；没有 header 时默认 `wiki-study`。

> 目前没有 key；header 可被伪造。仅内部信任网络使用。未来改成 API key -> role，不改工具接口。

## 4. 内容审核

不做入库审核/staging。

```text
ingest
  -> canonical claims
  -> conflict scan
  -> Conflicts 人工审核
```

`wiki-work` 可以直接 ingest；`wiki-manage/admin` 审核冲突。

## 5. 删除回滚

`DELETE /api/documents/{id}` 现在会：

- 删除 raw claims / evidence
- 重算 canonical evidence_count
- 删除无 evidence 的 canonical claim
- 删除相关 contradiction/adjudication
- 标记 Wiki stale / enqueue rebuild

这是“防误操作”，不是入库审批。

## 6. 安全边界

> ⚠ **本节描述的信任模型已被取代。** 新的身份接入与权限设计见
> [`auth-oidc.md`](./auth-oidc.md)（外部身份源 → 本地用户表 → 映射 → 角色 + `kb_scope` + 审计），
> 2026-11-19 已实现。

- ~~角色 header/cookie 可伪造~~ → 角色不再由客户端自报；请求级降级只能**降**不能升
- ~~无用户系统~~ → 身份由外部源提供（OIDC / 微信），本地只做授权
- ~~无 API key~~ → 超级用户与敏感操作使用 `SOFTWIKI_SUPERUSER_TOKEN` / `SOFTWIKI_REAUTH_TOKEN`
- 仍成立：对外部署必须加 TLS / 反代；`X-SoftWiki-Role` 不再被读取

**历史缺陷（已修复）**：

- `softwiki/api/server.py` 角色中间件曾默认回退到 `wiki-admin`；
- `softwiki/permissions.py` 的 `normalize_role()` 曾对未知角色回退到 `wiki-admin`；
- 两者合起来意味着「角色写错 = 拿到最高权限」；现已改为 fail-closed（回退 `wiki-study`）。

## 7. 实现状态

- [x] `permissions.yaml` + capability checker
- [x] API role middleware（header/cookie/env）
- [x] Web 角色选择器
- [x] MCP role header middleware
- [x] MCP 工具 capability guard
- [x] document delete canonical cleanup
- [x] team trial mapping（work 可 ingest/index）
- [x] API key -> role（token 已落，见 `auth-oidc.md` §5）
- [x] 外部身份接入（OIDC / 微信 adapter）
- [x] 审计日志 / 降级工作模式 / 超级用户窗口
- [ ] 管理面 UI（当前只有 `/api/admin/*` 接口）
- [ ] 管理员放行 `pending` 用户的界面

> 后续方向已明确：不做用户系统，改为**接外部身份源**（OIDC / 微信 / 客户自有），
> 见 [`auth-oidc.md`](./auth-oidc.md)。
