# Team Trial Runbook

> 目标：内部小团队试用；不做用户系统、不做 API key、不做端口拆分。
> 角色是**自报的信任型控制**，不是安全边界。

## 1. 入口

```text
Web:   http://10.3.9.29:6108
API:   http://10.3.9.29:6200   (Web 内部使用/管理员)
MCP:   http://10.3.9.29:6100/mcp
Agent: http://10.3.9.29:6111
```

单 MCP 端口；不拆 read/write 端口。

## 2. 角色

```text
wiki-study   只读
wiki-work    只读 + Wiki + ingest/index（team trial 允许 Hermes 直接输入）
wiki-manage  内容管理 + publish + adjudicate
wiki-admin   全部
```

默认角色是 `wiki-study`。

## 3. Web

左侧工作区下方有角色选择器。切换后写 cookie：

```text
softwiki_role=wiki-admin
```

刷新页面生效。Demo 开始前切到 `Admin`。

## 4. Hermes / MCP

157 上已部署 Hermes Agent + WebUI：

```text
Dashboard: http://117.133.38.157:9119
Gateway:   127.0.0.1:8642 only
MCP Coffee: softwiki_coffee -> http://host.docker.internal:6100/mcp
MCP AI:     softwiki_ai     -> http://host.docker.internal:6102/mcp
Role:       wiki-work
```

Dashboard 登录：`admin` / 见 `/opt/aitools/apps/hermes/.env`。



Hermes 配置：

```json
{
  "mcpServers": {
    "softwiki": {
      "url": "http://10.3.9.29:6100/mcp",
      "headers": {
        "X-SoftWiki-Role": "wiki-work"
      }
    }
  }
}
```

- 没有 header 时默认 `wiki-study`
- `wiki-work` 在 team trial mapping 中允许 `ingest.write` / `index.write`
- 内容冲突仍由 `wiki-manage/admin` 在 Conflicts 面板审核

## 5. opencode

- 每个 opencode session 传自己的 `X-SoftWiki-Role`
- TUI 切角色后应新建 session；不要让旧 session 沿用旧角色
- 没有 header 时只读

## 6. Mapping 文件

```text
/opt/aitools/apps/softwiki/workspace/armkb/config/permissions.yaml
```

修改后重启 API/MCP：

```bash
docker compose -f ~/softwiki-ci/docker-compose.yml --project-name softwiki restart api mcp
```

默认 mapping 在 `softwiki/permissions.py`；文件存在时覆盖默认。

## 7. 当前 Session 边界

- Web chat sessions：浏览器 `localStorage`，不同浏览器分开；同一浏览器 profile 共享
- SWAgent session：Web session -> opencode session 映射存在 localStorage
- MCP：transport session + role header
- 还没有服务端 `chat_sessions` / 跨设备恢复 / 用户级隔离

内部小团队够用；如果要跨设备/严格隔离，再加服务端 session。

## 8. 直接 ingest 的边界

Team trial 不做 staging / 入库审批。

```text
Hermes/work -> ingest -> canonical claims -> conflict scan -> Conflicts 人工审核
```

删除文档会清理：

- raw claims / evidence
- canonical evidence_count / 空 canonical
- contradiction/adjudication
- wiki stale + rebuild queue

这降低误操作风险，但不是审批。

## 9. 安全检查

- 不要把 6100/6200 暴露到公网
- 角色 header/cookie 可伪造
- 对外前必须加 API key / auth / TLS
- 不在聊天/截图里展示 `.env`、密钥、Postgres 密码
