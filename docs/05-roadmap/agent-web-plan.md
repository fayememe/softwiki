# Agent Web / opencode 集成计划

> status: 🚧 讨论中（2026-10-24）
> 目标：把 TUI 的 opencode agent 能力带到 Web，同时保留现有 Quick Answer 的知识库页码引用。
> 非目标：本期不做权限/多租户；不是把 chat 整个替换掉。

---

## 1. 现状（代码事实）

### 1.1 TUI 的集成方式

`softwiki/cli/shell.py`：

```python
opencode_path = shutil.which("opencode")
...
os.environ["XDG_CONFIG_HOME"] = runtime_dir
os.environ["XDG_DATA_HOME"]   = runtime_dir
...
os.execvp("opencode", ["opencode", "--agent", mode, "--continue", abs_project_root])
```

| 项 | 现状 |
|---|---|
| opencode 二进制 | **系统/全局安装**，SoftWiki 不打包、不锁版本 |
| 配置 | 隔离：`.softwiki_runtime/<ws>_<hash>/opencode/opencode.json` |
| 会话/数据 | 隔离：`XDG_DATA_HOME` 指到同一 runtime 目录 |
| 模式/提示词 | 隔离：动态生成 `AGENTS_wiki-*.md` |
| 插件 | **不完全隔离**：读全局 `opencode.jsonc` 的 plugin、复制全局 `tui.json`、symlink 全局 `node_modules` |
| MCP | 合并全局 MCP + softwiki MCP |
| 文件系统/网络 | **没有沙盒**，是当前用户权限；prompt 级“不要离开 workspace”不是强制边界 |

结论：**profile 是自己的，运行时是隔离的，二进制是系统的，安全边界是 prompt 级的。**

### 1.2 当前 TUI 的 agent 定位

`softwiki/templates/agent_soul.md` 明确禁止：

| 禁止在 Shell 使用 | 原因 |
|---|---|
| `softwiki_search` | 用原生 websearch |
| `softwiki_ask` | 用自己推理 |
| `softwiki_retrieve` | 用原生能力 |
| `graph/timeline/claim_query` | 给外部 agent 用 |

所以 TUI 是**研究/入库管理员**，不是“基于 kb-alpha 的问答”。它可能更聪明，但结论不一定来自知识库。

### 1.3 当前 Web Chat

`web/components/ChatPanel.tsx` → `POST /api/ask` → `AnswerEngine.ask`：

- 一次 RAG/claims/graph/timeline/wiki 检索
- 一次 LLM 调用
- 输出带页码的引用
- 无工具循环、无 websearch（除非开服务端搜索）、无多步规划

### 1.4 build-host 现有 opencode

- 版本：`1.18.35`
- 二进制：`/home/operator/.opencode/bin/opencode`
- 全局 server：`:4096`（Basic auth）
- 全局 web：`:4097`（Basic auth）
- 两者都不是 SoftWiki 专用，**不复用**

---

## 2. 产品形态：双模式

同一个聊天窗口两个按钮：

```
[ Quick Answer ]  [ Agent / Deep Research ]
```

| 模式 | 引擎 | 优点 | 代价 |
|---|---|---|---|
| Quick Answer | `AnswerEngine` | 快、基于 kb-alpha、页码引用 | 单轮，不会多步研究 |
| Agent | opencode | 多步、websearch、工具调用、研究能力 | 慢、需要沙盒/版本管理 |

**为什么不是直接换掉 chat**：Quick Answer 的“可溯源”是 demo 的核心；Agent 的“聪明”是研究能力。两者互补。

---

## 3. 实现层级

### L1（先做，低成本）

1. 抽出 shell 的运行时生成逻辑为共享函数：`prepare_agent_runtime(workspace, mode)`。
2. 新增 CLI：`softwiki agent-web`
   - 生成同一套 `opencode.json` / `AGENTS_wiki-*.md`
   - 设置隔离的 `XDG_CONFIG_HOME` / `XDG_DATA_HOME`
   - `exec` `opencode web --port 6111 --hostname 0.0.0.0`
3. WebUI 增加 **Agent / Deep Research** 入口（新 tab 或 iframe）指向 `http://build-host:6111`。
4. 保留现有 Chat 的 Quick Answer。
5. **给 Agent 打开知识库工具**：
   - 允许 `softwiki_search` / `softwiki_retrieve`（可选 `softwiki_ask`）
   - 系统提示要求：每个结论来自 KB 命中或明确标注来自 web；引用带页码
6. Shell 模型配置：
   - 当前 build-host 的 Google key 已 402
   - 用 `SHELL_MODEL` / `SHELL_API_BASE` / `SHELL_API_KEY` 指到可用的 OpenAI/DeepSeek

### L2（产品化，后续）

1. Next.js ChatPanel 增加 Agent 模式。
2. FastAPI 增加 `/api/agent/*` 代理：
   - `POST /api/agent/session` → opencode `POST /session`
   - `POST /api/agent/message` → opencode `POST /session/:id/message`
   - `GET /api/agent/event` → opencode `GET /event`（SSE）
3. 前端流式输出、工具调用可视化、会话管理、abort。
4. Agent 与 Quick Answer 共用同一个输入框和会话列表。

---

## 4. 打包方案

| 方案 | 做法 | 适用 |
|---|---|---|
| A. 打进 SoftWiki 镜像 | Dockerfile 固定版本安装 opencode，绝对路径调用 | 单镜像、简单交付 |
| **B. 独立 `softwiki-agent` 容器（推荐）** | 固定版本 opencode；独立升级；挂 runtime/session volume；API/WebUI 通过 HTTP 访问 | 产品化、可回滚、可沙盒 |
| C. 宿主 opencode（现状） | 依赖客户环境 | 只适合开发 |

方案 B 要点：

- 固定 `OPENCODE_VERSION`（当前 `1.18.35`）
- **不读全局 opencode 配置**；只用 SoftWiki 生成的配置
- 插件固定版本，或 `--pure` 关闭
- 容器内挂载 workspace；限制工具/网络
- MCP：同镜像内 stdio，或 SoftWiki 的 HTTP MCP
- `XDG_DATA_HOME` 挂 volume，保留会话

---

## 5. 升级流程

1. bump `OPENCODE_VERSION` + agent 镜像 tag
2. 构建 agent 镜像
3. 冒烟测试：
   - `GET /agent` 能看到 4 个 `wiki-*` agent
   - 创建 session、发一条测试消息
   - 调 `softwiki_status` / `softwiki_search`
   - 确认模型/MCP/workflows 正常
4. 保留上一个镜像 tag 回滚
5. session volume 不动；如果 opencode 会话格式变化，做迁移或旧会话只读
6. 配置 schema 变化纳入测试，不假设旧 `opencode.json` 永远兼容

---

## 6. 任务拆分

### P0（L1 demo）

- [ ] 抽出 `prepare_agent_runtime()`（shell 与 agent-web 共用）
- [ ] `softwiki agent-web` CLI（隔离 XDG + `opencode web`）
- [ ] WebUI 增加 Agent 入口
- [ ] Agent 模式允许 `softwiki_search` / `retrieve`
- [ ] Agent 提示词加“页码引用 + 不足则弃权”
- [ ] 设置 `SHELL_MODEL` / `SHELL_API_BASE` / `SHELL_API_KEY`
- [ ] 验收：浏览器打开 `:6111`，问 PL031，能调 KB 工具并给页码

### P1（L2 产品化）

- [ ] FastAPI `/api/agent/*` 代理（session/message/event）
- [ ] 前端 Agent 模式、流式、工具调用展示
- [ ] 双模式切换与会话映射
- [ ] 独立 `softwiki-agent` 容器 + 固定版本
- [ ] 升级冒烟测试 + 回滚
- [ ] 会话 volume 备份/恢复

### 暂不做

- 权限/登录/多租户（demo 阶段）
- 完全替换 Quick Answer
- 复用全局 `:4096` / `:4097`

---

## 7. 风险

- opencode 版本漂移：必须 pin 版本 + 冒烟测试
- 全局插件/MCP 污染：产品化必须不读全局配置
- 当前没有 OS 级沙盒：容器化前不能给不可信用户
- TUI 默认不读 KB：不打开 `softwiki_search/retrieve` 就不是“基于知识库的聪明”
- Google key 402：Shell 模型必须切到可用 provider

---

## 8. 验收（L1）

1. `softwiki agent-web` 启动成功，`:6111` 可访问
2. Web UI 能选到 4 个 `wiki-*` agent
3. 提问 `What registers does the PL031 RTC provide?`
   - 能调 `softwiki_search` / `retrieve`
   - 答案带页码
4. 现有 Quick Answer 仍正常，带页码引用
5. 关闭 agent 进程后不影响 SoftWiki API

---

## 9. 实施记录（2026-10-24）

### L1 已上线并验证

- `softwiki agent-web --port 6111 --host 0.0.0.0 --mode wiki-research`
- `prepare_agent_runtime(web=True)`：生成 `AGENTS_wiki-research.md`、`default_agent=wiki-research`、隔离 `XDG_*`
- 浏览器 agent 通过 **现有 MCP 服务** `http://127.0.0.1:6100/mcp`（remote）访问 KB，不在宿主安装 psycopg2
- `wiki-research` 权限：`bash`/`edit` deny；`softwiki_ingest`/`index`/`rebuild_index`/`wiki_build`/`modules_set`/`workspace_set` deny；`steps=8`
- WebUI：Sidebar **Agent** 入口 + ChatPanel **Agent ↗** 入口；`web/lib/agent.ts` 按当前 hostname 生成 `:6111` URL
- build-host：`softwiki-agent-web.service`（systemd，host opencode `1.18.35`，端口 `6111`）
- Shell 模型：`SHELL_MODEL=gpt-4.1-mini`（`gpt-5-mini` 不接受 `max_tokens`）

### L2 已上线并验证（非流式）

- FastAPI：
  - `GET /api/agent/status`
  - `POST /api/agent/session`
  - `POST /api/agent/ask`（轮询 opencode session，返回 answer/sources/tools）
  - `POST /api/agent/session/{id}/abort`
  - `DELETE /api/agent/session/{id}`
- WebUI：ChatPanel **Quick / Agent** 切换；Agent 模式显示 research steps、工具调用、解析后的 KB sources；会话映射存在 localStorage
- Docker：API 通过 `AGENT_WEB_URL=http://host.docker.internal:6111` 访问宿主 agent；`extra_hosts: host-gateway`
- 注意：当前是**非流式**；SSE/逐 token 输出留到后续

### 已知问题 / 待验证

- 2026-10-24 首次验收时，agent 经 remote MCP 调用了 `softwiki_rebuild_index`，触发全量索引；已 abort/restart，随后执行全量 `index` 修复。**在索引完成前，`softwiki_search` 返回空。**
- 本次事件证明：**prompt + opencode permission 两层还不够**；产品化应增加只读 MCP sidecar / 网关。
- 索引已完成（39,870 chunks），并已验证：
  1. `softwiki_search` 返回 PL031 结果
  2. `/api/agent/ask` 返回答案 + sources + tools（约 20–40s）
  3. WebUI Agent 模式正常（Playwright：2 个 research steps、答案、1 source）
  4. `scripts/run_acceptance.py` **11/11**
- L1 仍是宿主 opencode `1.18.35`；独立 `softwiki-agent` 容器留给产品化。
- L2 目前是轮询非流式；SSE / 逐 token 是下一步。
- **Next rewrite 默认 30s** 会先于 `AGENT_TIMEOUT=300` 超时，导致前端误报 `Invalid response`；已在 `web/next.config.ts` 设 `experimental.proxyTimeout=300_000`。
- Agent 入口使用同源 `/agent` 307 → 当前 host:6111，避免服务端渲染写死 localhost。
- Agent source 卡片：从答案引用解析出的 citation 没有检索 score；已改为按标题/页码反查 KB 的 `source_name`/日期/摘录，score 缺失时 UI 隐藏百分比，不再显示误导性的 0%。
- 系统提示词要求快路径：`softwiki_ask` 一次 + `softwiki_search` 一次；实测 2 个工具、约 40s。
- 2026-10-24 修复：`AnswerEngine` 把 "List/Summary" 研究问题误判为 inventory；`softwiki_ask` 不再返回工作区统计。
