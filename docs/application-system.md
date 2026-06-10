> [!NOTE]
> **本文档为参考文档，不作为设计要求。**
> 本文记录了架构讨论与设计思考过程，部分内容超出当前实现范围，仅供参考。
> 以实际代码实现为准，以 [project-status.md](project-status.md) 为当前状态说明文档。

# SoftWiki Core 外部架构总结

## 1. 文档范围

本文描述 SoftWiki Core 与其外部系统之间的架构边界。

SoftWiki Core 已经存在，并且可以完成知识库相关业务逻辑。本文不重新设计 Core 内部的 RAG、GraphRAG、LLM-Wiki、综合器、索引、图谱等实现。

本文重点覆盖：

* Core 与外部工具的职责边界
* 子项目拆分
* MCP 服务暴露方式
* 远程 MCP 访问
* WebUI 定位
* Shell / TUI 定位
* 外部客户端工具
* raw data 输入边界
* filesystem-based source model
* token 与权限模型
* team 部署方式

---

# 2. 核心原则

SoftWiki Core 不是 dumb backend。
SoftWiki Core 应该负责知识库领域内的业务逻辑。

但是 SoftWiki Core 不应该变成通用 Agent 平台。

正确边界是：

```text
SoftWiki Core = knowledge-domain business logic
External Tools = user-facing / cross-domain agent workflow
MCP = capability boundary
Filesystem = raw data boundary
```

中文解释：

```text
SoftWiki Core 负责知识库自己的业务闭环。
外部工具负责自己的 Agent、模型、UI 和跨工具任务编排。
MCP 用于暴露 SoftWiki 能力。
Filesystem 是 SoftWiki 的正式 raw data 输入边界。
```

---

# 3. SoftWiki Core 应该负责什么

Core 可以并且应该完成知识库相关业务逻辑，包括：

```text
source scan
metadata / hash / dedup
ingest
chunk / index
RAG / Graph / Wiki / Claims / Timeline build
wiki generation
claim extraction
conflict detection
freshness detection
answer synthesis
citation / provenance
eval
publish / rollback
workspace status
```

这些属于知识库领域内的业务逻辑，不应该全部交给外部 Agent 临时拼装。

Core 可以使用 LLM-powered internal workflow / internal agent 完成领域任务，例如：

```text
contextual chunking
entity extraction
relation extraction
claim extraction
wiki generation
query rewrite
answer synthesis
eval generation
conflict explanation
build diagnosis
```

但是 Core 不负责：

```text
通用 coding agent
通用 browser agent
通用办公 agent
论文/报告/项目任务的完整跨工具编排
用户外部文件系统管理
外部工具的模型选择
外部工具的 agent loop
```

---

# 4. Core Agent 与外部 Agent 的区别

| 类型                             | 属于谁                                     | 负责什么                                                | 不负责什么                          |
| ------------------------------ | --------------------------------------- | --------------------------------------------------- | ------------------------------ |
| Core internal agent / workflow | SoftWiki Core                           | 知识库内部任务：ingest、build、wiki、claim、answer、eval、publish | 通用用户任务、IDE 操作、跨工具规划            |
| Shell assistant                | SoftWiki Shell                          | 帮 admin / maintainer 操作 SoftWiki                    | 通用 coding/browser/office agent |
| WebUI ask                      | SoftWiki Web                            | 调用 Core 的 ask/search/wiki 能力                        | 自己重做复杂 agent loop              |
| External tool agent            | opencode / Claude / Cursor / custom app | 用户任务、模型选择、多工具编排                                     | SoftWiki Core 内部状态管理           |

关键原则：

```text
SoftWiki Core 要足够聪明，能完成知识库自己的业务；
但不要成为所有客户端的通用大脑。
```

---

# 5. 高层架构

```text
                 External Raw Data Producer
                 human / script / git / rsync /
                 rclone / crawler / Hermes / etc.
                              |
                              v
                    Filesystem / Mounted Folder
                              |
                              v
                    SoftWiki Source Scanner
                              |
                              v
+---------------------------------------------------------------+
|                       SoftWiki Core                           |
|  knowledge-domain business logic                              |
|  ingest / index / wiki / graph / claims / answer / publish    |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|                    SoftWiki Server / MCP Gateway              |
|  auth / RBAC / audit / HTTP API / MCP tools                   |
+---------------------------+-----------------------------------+
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
   WebUI Client        Shell / TUI Client   External MCP Clients
   human portal        power interface      opencode / Claude /
                                           Cursor / Zed / apps
```

---

# 6. 推荐子项目划分

SoftWiki 应采用分离式子项目架构。

可以是 multi-repo，也可以是 monorepo packages。

推荐逻辑模块：

```text
softwiki-core
softwiki-server
softwiki-mcp
softwiki-web
softwiki-cli
softwiki-shell
softwiki-bridge
softwiki-apps
```

如果采用 monorepo：

```text
softwiki/
  packages/
    core/
    server/
    mcp/
    web/
    cli/
    shell/
    bridge/
    sdk/
    apps/
```

---

# 7. 各子项目职责

## 7.1 softwiki-core

职责：

```text
workspace knowledge runtime
source scan
ingest
index
search
retrieve
wiki
graph
claims
timeline
synthesizer
conflict detection
freshness detection
eval
publish / rollback
```

可以包含：

```text
knowledge-domain internal agent / workflow
```

不负责：

```text
WebUI
Shell UI
第三方 Agent
通用任务规划
crawler
raw data acquisition
用户模型配置
IDE / coding workflow
```

---

## 7.2 softwiki-server

职责：

```text
对外服务进程
HTTP API
auth
RBAC
token 校验
audit log
workspace routing
调用 softwiki-core
```

不负责：

```text
前端页面
外部 Agent 决策
raw data 获取
```

---

## 7.3 softwiki-mcp

职责：

```text
MCP Gateway
MCP tool definitions
MCP request/response adapter
tool-level authorization
stdio MCP server
remote HTTP MCP endpoint
```

它把 Core 的 domain-level capability 包装成 MCP tools，例如：

```text
softwiki.ask
softwiki.search
softwiki.retrieve
softwiki.wiki.read
softwiki.source.preview
softwiki.graph.query
softwiki.timeline.query
softwiki.claim.query
softwiki.upload.submit
softwiki.ingest.request
softwiki.publish
```

MCP 暴露的是 domain capability，不是 Core 内部零件。

不推荐暴露过低层接口：

```text
softwiki.get_embeddings
softwiki.get_raw_chunks_without_policy
softwiki.run_arbitrary_prompt
softwiki.agent_do_everything
```

---

## 7.4 softwiki-web

职责：

```text
WebUI
Dashboard
Ask/Search 页面
Wiki Web
Source Browser
MCP setup page
Admin status 页面
```

WebUI 是独立客户端。

```text
WebUI 通过 HTTP API 或 MCP-backed API 调用 softwiki-server。
WebUI 不直接访问 Core 内部对象、vector DB、graph DB 或 raw data。
```

第一阶段 WebUI 可以以只读为主：

```text
ask
search
browse wiki
view sources
view citations
view build status
view MCP config
```

后续可以支持轻量贡献：

```text
submit note
upload document
propose wiki edit
save answer
request re-index
```

---

## 7.5 softwiki-cli

职责：

```text
命令行管理工具
token create/revoke
workspace status
source scan
ingest run
mcp config generation
remote login
```

示例：

```bash
softwiki token create --workspace chip-kb --role wiki-study
softwiki source scan --workspace chip-kb
softwiki ingest run --workspace chip-kb
softwiki mcp config --client opencode --workspace chip-kb
```

---

## 7.6 softwiki-shell / TUI

职责：

```text
maintainer / power user 操作界面
交互式 workspace 操作
诊断
build / publish 控制
answer trace inspection
```

Shell 可以有轻量内部助手，但 scope 限制在 SoftWiki operations。

```text
Shell Agent scope = SoftWiki operations only.
```

不应变成：

```text
通用 coding agent
通用 browser automation
通用办公 agent
```

---

## 7.7 softwiki-bridge

职责：

```text
stdio-to-remote MCP bridge
兼容只支持 stdio MCP 的客户端
```

数据流：

```text
External MCP Client
  -> local stdio bridge
  -> HTTPS remote SoftWiki MCP
  -> SoftWiki Server
```

示例：

```json
{
  "mcpServers": {
    "softwiki-chip-kb": {
      "command": "softwiki",
      "args": [
        "mcp",
        "bridge",
        "--url",
        "https://kb.example.com",
        "--workspace",
        "chip-kb"
      ],
      "env": {
        "SOFTWIKI_TOKEN": "..."
      }
    }
  }
}
```

---

## 7.8 softwiki-apps

未来生产力工具放这里，作为独立客户端。

例如：

```text
paper writer
report generator
result submission tool
review assistant
research workspace
```

这些 app 可以有自己的 Agent：

```text
自己配置 LLM
自己规划任务
自己调用 SoftWiki MCP
自己调用其他工具
```

SoftWiki Core 不承载这些 Agent。

---

# 8. 子项目之间如何互通

## 8.1 Core 与 Server

```text
server -> core internal API
```

这是内部调用，可以使用本地 library API 或 RPC。

---

## 8.2 Server 与 WebUI

```text
web -> HTTP API -> server -> core
```

WebUI 不直接访问 Core。

---

## 8.3 Server 与外部 Tool

```text
external tool -> MCP -> softwiki-mcp/server -> core
```

MCP 是外部工具的正式能力边界。

---

## 8.4 Shell 与 Server/Core

本地模式：

```text
shell -> core/server local API
```

远程模式：

```text
shell -> HTTPS API/MCP -> server -> core
```

---

## 8.5 Raw Data Producer 与 SoftWiki

正式输入边界是 filesystem：

```text
external producer -> filesystem -> softwiki source scanner -> core ingest
```

External producer 可以是任意东西：

```text
manual copy
rsync
git
rclone
wget
crawler
Hermes
company sync tool
```

但它们都不属于 SoftWiki 开发范围。

---

# 9. 知识输入边界

SoftWiki 不负责开发、维护或集成 Hermes / crawler / importer / sync tool。

SoftWiki 不关心用户如何获得 raw data。

用户可以用任意方式准备 raw data，例如：

```text
手工复制文件
git clone / git pull
rsync
rclone
wget / curl
自己写脚本
公司内部同步工具
Hermes
crawler
downloader
exported Confluence / Google Drive / Notion data
```

这些都不属于 SoftWiki 的开发范围。

SoftWiki 的正式输入边界是：

```text
filesystem
```

也就是：

```text
用户把 raw data 放到 SoftWiki workspace 可访问的目录里。
SoftWiki 从这些目录读取、扫描、登记、ingest。
```

---

# 10. Workspace 输入目录

推荐 workspace 结构：

```text
workspace/
  sources/
    docs/
    papers/
    repos/
    web/
    exports/

  uploads/
    users/
    agents/
    tools/

  softwiki.yaml
  sources.yaml
```

其中：

```text
sources/ = 已注册的 raw data source
uploads/ = 用户或外部工具提交的待处理资料
```

也可以允许用户把真实 raw data 放在 workspace 外部，然后通过 manifest 指向它：

```yaml
sources:
  - id: project-docs
    type: filesystem
    path: /data/team/project-docs
    include:
      - "**/*.md"
      - "**/*.pdf"
    exclude:
      - "**/archive/**"

  - id: exported-confluence
    type: filesystem
    path: /mnt/share/confluence-export
    include:
      - "**/*.html"
      - "**/*.md"

  - id: git-checkout
    type: filesystem
    path: /data/repos/project
    include:
      - "docs/**"
      - "README.md"
```

即使数据来源原本是 Git、Confluence、Google Drive、Hermes 或 crawler，SoftWiki 看到的仍然只是 filesystem path。

---

# 11. 外部工具如何接入 raw data

外部工具不需要使用 SoftWiki 专用协议。

只要能把文件写入 SoftWiki 可访问目录即可。

示例：

```bash
# 用户自己同步
rsync -av ./docs/ /data/softwiki/workspaces/chip-kb/sources/docs/

# 用户自己下载
wget -P /data/softwiki/workspaces/research-kb/sources/web/ https://example.com/page.html

# 用户自己 clone
git clone git@github.com:org/project.git /data/softwiki/workspaces/chip-kb/sources/repos/project

# 用户自己用 rclone
rclone sync gdrive:team-docs /data/softwiki/workspaces/team-kb/sources/docs
```

SoftWiki 只需要：

```bash
softwiki source scan --workspace chip-kb
softwiki ingest run --workspace chip-kb
```

或者自动 watch / schedule scan。

---

# 12. MCP 写入工具定位

MCP 写入工具可以保留，但不作为主要 raw data 输入路径。

建议定位：

```text
MCP 写入 = 轻量 contribution / upload / submit
filesystem = 正式 raw data 输入边界
```

外部 Agent 可以调用：

```text
softwiki.upload.submit
softwiki.submit.note
softwiki.propose.wiki_edit
```

但这些内容最终仍应落到：

```text
workspace/uploads/
```

或者等价 staging area。

不要让 MCP submit 绕过 filesystem / staging / source tracking 直接进入正式知识库。

---

# 13. Staging 与 Publish

外部写入不应该直接修改正式知识库。

推荐流程：

```text
external tool writes file
  -> uploads/
  -> SoftWiki scan
  -> hash / metadata / dedup
  -> ingest draft
  -> optional review
  -> publish
```

权限规则：

```text
wiki-work 只能写 uploads/staging。
wiki-manage 才能把内容纳入正式 source / publish。
```

---

# 14. MCP Transport 与远程访问

SoftWiki 应支持三种 MCP 使用方式。

---

## 14.1 Local stdio MCP

适合只支持本地 MCP server 的客户端。

```text
client -> stdio -> local softwiki MCP server
```

示例配置：

```json
{
  "mcpServers": {
    "softwiki": {
      "command": "softwiki",
      "args": ["mcp", "serve", "--workspace", "my-kb"]
    }
  }
}
```

---

## 14.2 Remote HTTP MCP

适合 team / cloud 部署。

```text
client -> HTTPS Streamable HTTP MCP -> SoftWiki server
```

示例 endpoint：

```text
https://kb.example.com/mcp
https://kb.example.com/mcp/workspaces/chip-kb
```

示例配置：

```json
{
  "mcpServers": {
    "softwiki-chip-kb": {
      "url": "https://kb.example.com/mcp/workspaces/chip-kb",
      "headers": {
        "Authorization": "Bearer ${SOFTWIKI_TOKEN}"
      }
    }
  }
}
```

---

## 14.3 Local stdio-to-remote bridge

有些客户端只支持 stdio，但实际需要访问远程 SoftWiki server。
这种情况下应提供本地 bridge。

```text
client -> stdio -> softwiki bridge -> HTTPS -> SoftWiki server
```

示例配置：

```json
{
  "mcpServers": {
    "softwiki-chip-kb": {
      "command": "softwiki",
      "args": [
        "mcp",
        "bridge",
        "--url",
        "https://kb.example.com",
        "--workspace",
        "chip-kb"
      ],
      "env": {
        "SOFTWIKI_TOKEN": "..."
      }
    }
  }
}
```

这个 bridge 对兼容不同 MCP client 很重要。

---

# 15. Team 部署模型

推荐 team 部署：

```text
Admin 在 cloud 或内网部署 SoftWiki server。
SoftWiki 暴露 WebUI + MCP + optional HTTP API。
Team member 用 WebUI 阅读和搜索。
Power user 用 Shell / TUI。
外部 client tool 通过 MCP 连接。
```

不要要求普通用户都 SSH 登录服务器。

推荐角色入口：

```text
Admin:
  SSH + shell + server config

Maintainer:
  shell / TUI + Web admin

Contributor:
  WebUI contribution + limited MCP tools

Reader:
  WebUI read-only + read-only MCP tools
```

---

# 16. WebUI 模块建议

SoftWiki WebUI 应该模块化。

MVP 模块：

```text
/                 Dashboard
/ask              Ask / search with citations
/wiki             Wiki homepage
/wiki/:page       Wiki page with provenance / citations
/sources          Source list
/sources/:id      Source detail
/mcp              MCP setup / config page
/admin/status     Build / index / publish status
```

后续模块：

```text
/entities         Entity browser
/entities/:id     Entity page
/timeline         Workspace timeline
/claims           Claim DB view
/conflicts        Conflict detector
/evals            Eval dashboard
/review           Review queue
/submissions      Contribution / submission system
/reports          Report / paper generation tools
```

推荐前端组件策略：

```text
Chat / Ask:
  assistant-ui 或 Vercel Chatbot 风格组件

Dashboard:
  shadcn/ui + charts

Wiki:
  自定义 Markdown/MDX renderer + citation/freshness/sidebar

Graph:
  Cytoscape.js 做 entity graph
  React Flow 做 provenance / pipeline / trace graph

Tables:
  TanStack Table

Charts:
  Recharts

Source viewer:
  Markdown renderer
  PDF.js
  CodeMirror / Monaco
```

不要 fork 一个完整 RAG/wiki 产品作为主 WebUI。
应使用 UI library / component，而不是继承别人的信息架构。

---

# 17. 安全模型

远程 MCP 必须按生产 API 对待。

最低要求：

```text
HTTPS only
Bearer token 或 OAuth/OIDC
token expiration
workspace-scoped access
role-based authorization
tool-level allowlist
parameter-level validation
audit log
rate limiting
read/write tool separation
```

不要裸露远程 MCP。

---

# 18. Token 模型

Token 应代表：

```text
identity + workspace scope + role + allowed tools + expiration
```

概念 schema：

```ts
type SoftWikiToken = {
  id: string
  name: string
  subject: string              // user, service, agent
  token_hash: string
  role: "wiki-admin" | "wiki-manage" | "wiki-work" | "wiki-study"
  workspace_scope: string[] | "*"
  allowed_tools?: string[]
  denied_tools?: string[]
  allowed_paths?: string[]
  expires_at?: string
  created_at: string
  last_used_at?: string
  revoked_at?: string
}
```

只保存 token hash。
创建后不要保存明文 token。

---

# 19. Role 模型

SoftWiki 权限角色：

```text
wiki-admin  : system god
wiki-manage : workspace maintainer
wiki-work   : workspace contributor / uploader
wiki-study  : workspace reader
```

---

## 19.1 wiki-admin

Scope：

```text
system-wide
```

可以：

```text
管理所有 workspace
管理 users / tokens
修改 system config
访问所有 tools
```

应谨慎使用。

---

## 19.2 wiki-manage

Scope：

```text
one or more workspaces
```

可以：

```text
register sources
scan sources
run ingest
build wiki / graph / claims / timeline
run eval
approve submissions
publish workspace
rollback workspace
view audit
```

不能：

```text
管理整个系统
访问无关 workspace
修改全局安全配置
```

---

## 19.3 wiki-work

Scope：

```text
one or more workspaces
```

可以：

```text
read workspace
ask / search / retrieve
read wiki
submit / upload to staging or upload folder
propose wiki edits
submit notes / results
request ingest
```

不能：

```text
publish
delete sources
change schema
change workspace config
directly modify published wiki
directly modify canonical source store
```

关键规则：

```text
wiki-work 只能写 staging / upload，不能直接 publish。
```

---

## 19.4 wiki-study

Scope：

```text
one or more workspaces
```

可以：

```text
ask
search
retrieve
read wiki
query graph / timeline
view citation snippets
```

默认限制：

```text
no upload
no publish
no source mutation
no workspace export
no full raw source download unless explicitly allowed
```

注意：

```text
read-only 不等于可以读完整 raw source。
```

对 cloud-agent clients，默认只暴露必要 snippet。

---

# 20. Tool 权限映射

示例 role-to-tool mapping：

```yaml
roles:
  wiki-study:
    allow:
      - softwiki.ask
      - softwiki.search
      - softwiki.retrieve
      - softwiki.wiki.read
      - softwiki.source.preview
      - softwiki.graph.query
      - softwiki.timeline.query
      - softwiki.claim.query

  wiki-work:
    allow:
      - softwiki.ask
      - softwiki.search
      - softwiki.retrieve
      - softwiki.wiki.read
      - softwiki.source.preview
      - softwiki.graph.query
      - softwiki.timeline.query
      - softwiki.claim.query
      - softwiki.upload.submit
      - softwiki.submit.note
      - softwiki.submit.result
      - softwiki.propose.wiki_edit
      - softwiki.ingest.request

  wiki-manage:
    allow:
      - softwiki.ask
      - softwiki.search
      - softwiki.retrieve
      - softwiki.wiki.read
      - softwiki.wiki.build
      - softwiki.graph.query
      - softwiki.graph.build
      - softwiki.source.register
      - softwiki.source.scan
      - softwiki.ingest.run
      - softwiki.eval.run
      - softwiki.review.approve
      - softwiki.review.reject
      - softwiki.publish
      - softwiki.rollback

  wiki-admin:
    allow:
      - "*"
```

---

# 21. 授权流程

每次 MCP 请求都应经过：

```text
1. Validate token.
2. Check token is not expired or revoked.
3. Resolve subject, workspace scope, and role.
4. Check requested workspace is inside token scope.
5. Check role allows requested tool.
6. Check token-level allow/deny overrides.
7. Validate tool parameters for path/source/workspace escape.
8. Execute tool.
9. Write audit log.
```

参数级校验非常重要。

例如：

```text
wiki-work 可以调用 upload.submit，
但只能写入自己 workspace 内允许的 upload/staging path。
```

---

# 22. Audit Log

远程 MCP 和 WebUI 操作都应可审计。

Audit record 应包含：

```text
timestamp
subject
token_id
workspace
role
client_name
tool_name
request_id
success / failure
high-level parameters
source / document IDs touched
latency
error message if any
```

不要记录 raw secret 或完整敏感文档。

---

# 23. 推荐 MCP Tool 分类

## 23.1 Read Tools

```text
softwiki.ask
softwiki.search
softwiki.retrieve
softwiki.wiki.read
softwiki.source.preview
softwiki.graph.query
softwiki.timeline.query
softwiki.claim.query
```

## 23.2 Trace / Explain Tools

```text
softwiki.trace.answer
softwiki.explain.source
softwiki.find.conflicts
softwiki.find.stale
softwiki.citation.check
```

## 23.3 Contribution Tools

```text
softwiki.upload.submit
softwiki.submit.note
softwiki.submit.result
softwiki.propose.wiki_edit
softwiki.ingest.request
```

## 23.4 Maintainer Tools

```text
softwiki.source.register
softwiki.source.scan
softwiki.ingest.run
softwiki.wiki.build
softwiki.graph.build
softwiki.eval.run
softwiki.publish
softwiki.rollback
softwiki.review.approve
softwiki.review.reject
```

## 23.5 Admin Tools

```text
softwiki.workspace.create
softwiki.workspace.config
softwiki.user.manage
softwiki.token.create
softwiki.token.revoke
softwiki.system.status
```

---

# 24. 推荐部署结构

```text
softwiki-server:
  - access SoftWiki Core
  - MCP Gateway
  - HTTP API
  - auth / RBAC / audit

softwiki-web:
  - independent WebUI
  - talks to server API
  - no direct DB/index access

softwiki-cli:
  - admin commands
  - local shell
  - remote shell
  - MCP stdio bridge

softwiki-worker:
  - optional background worker
  - ingestion / build / publish jobs

storage:
  - existing SoftWiki core storage
  - upload / staging folder
  - audit DB
  - token DB
```

Docker deployment 可以包括：

```text
softwiki-server
softwiki-web
softwiki-worker
database
reverse proxy
```

---

# 25. 推荐 CLI 命令

```bash
softwiki server up

softwiki token create \
  --workspace chip-kb \
  --role wiki-study \
  --name opencode-reader

softwiki token create \
  --workspace ai-research \
  --role wiki-work \
  --name uploader

softwiki mcp serve \
  --workspace chip-kb

softwiki mcp bridge \
  --url https://kb.example.com \
  --workspace chip-kb

softwiki mcp config \
  --client opencode \
  --workspace chip-kb

softwiki shell

softwiki shell \
  --remote https://kb.example.com \
  --workspace chip-kb

softwiki source scan \
  --workspace chip-kb

softwiki ingest run \
  --workspace chip-kb
```

---

# 26. 项目间依赖规则

建议依赖方向：

```text
web        -> server API
cli        -> server API / local commands
shell      -> server API / local commands
mcp        -> server/core capability adapter
server     -> core
bridge     -> remote MCP
apps       -> MCP / HTTP API
core       -> no dependency on web/cli/shell/apps
```

禁止反向依赖：

```text
core must not depend on web
core must not depend on shell
core must not depend on external agent tools
core must not depend on Hermes/crawler
core must not depend on raw data acquisition tools
```

---

# 27. 关键设计原则

```text
1. SoftWiki Core 负责知识库领域内的业务闭环。
2. Core 可以有 internal agent / workflow。
3. Core 不做通用 Agent Host。
4. 外部工具拥有自己的 Agent、模型配置和任务编排。
5. MCP 是 SoftWiki 对外的能力边界。
6. WebUI 是独立的人类界面客户端。
7. Shell / TUI 是 maintainer / power user 的官方客户端。
8. 未来论文、报告、成果提交工具应作为独立 app，通过 MCP 调用 SoftWiki。
9. raw data acquisition 不属于 SoftWiki。
10. SoftWiki 的正式 raw data 输入边界是 filesystem。
11. 外部写入默认进入 staging / upload。
12. 只有 manager 可以 publish。
13. Token 必须绑定 workspace、role、tools、expiration。
14. Remote MCP 必须使用 HTTPS + auth + RBAC + audit。
15. read-only 用户不默认拥有完整 raw source 访问权。
16. 同时支持 remote HTTP MCP 和 local stdio bridge。
17. 不要把完整第三方 RAG/wiki 产品 merge 成 WebUI。
18. WebUI 可以使用 UI/component library，但 SoftWiki 自己控制信息架构。
```

---

# 28. 一句话总结

SoftWiki 应拆成多个分离子项目：Core 负责知识库领域内的完整业务逻辑和 internal workflow；Server/MCP 负责安全能力暴露；WebUI/Shell 是独立客户端；外部工具拥有自己的 Agent，并通过 MCP 调用 SoftWiki 的 domain-level capability；raw data acquisition 不属于 SoftWiki，正式输入边界是 filesystem。
