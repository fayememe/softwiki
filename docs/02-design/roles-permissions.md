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
http://10.3.9.29:6100/mcp
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

- 无用户系统
- 无 API key
- 角色 header/cookie 可伪造
- 只允许内部/受信网络
- 对外前必须加 token / auth / TLS

## 7. 实现状态

- [x] `permissions.yaml` + capability checker
- [x] API role middleware（header/cookie/env）
- [x] Web 角色选择器
- [x] MCP role header middleware
- [x] MCP 工具 capability guard
- [x] document delete canonical cleanup
- [x] team trial mapping（work 可 ingest/index）
- [ ] API key -> role（后续）
- [ ] 用户系统（后续）
