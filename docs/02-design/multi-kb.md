# 多 KB 支持（multi-kb）

> 状态：✅ frozen（v0 范围）
> 来源：讨论记录见本地 `mymd/F000-multi-kb.md`（不入库）
> 关联：`docs/05-roadmap/status.md`

## 1. 问题

一个 softwiki 实例当前只能服务**一个**知识库：

- `WORKSPACE_DIR` 是进程级环境变量，容器启动时固定；
- 请求级 override（`_request_workspace` ContextVar）只在 `SOFTWIKI_AUTH_ENABLED`
  打开时由 `auth_middleware` 设置（`api/server.py:146`）；
- MCP 的 `ask` / `search` 没有 `kb` 参数。

结果是「多个细分知识库」只能靠「每个库一套 API + MCP + Web + 数据库」实现，
agent 侧要挂 N 个 MCP 连接。

**目标**：一个 MCP 端口、一份进程服务全部知识库，提问时指定库；
agent 能先查询「有哪些库、各覆盖什么专题」，再决定问哪个。

## 2. 方案

### 2.1 核心机制：请求级 workspace

后端已经具备按 workspace 分派的基础设施：

| 能力 | 位置 |
|---|---|
| 请求级 workspace 上下文 `_request_workspace` | `config.py:34-46` |
| DB URL 按 workspace 派生 | `config.py:55-59` |
| 向量索引按 workspace 缓存（key 为完整路径） | `rag/vector_store.py:26` |
| BM25 索引同机制 | `rag/bm25_store.py:41` |

因此只需在**请求入口**设置 workspace，下游 DB / 向量 / BM25 自动跟随。
**不使用** `set_workspace_dir()`（它会写 `os.environ`，污染进程全局状态）。

### 2.2 MCP 工具契约

```python
kb_list() -> str
    """列出所有知识库及其覆盖专题。首要调用，零 DB 开销。"""

kb_describe(kb: str) -> str
    """展开单个库的完整信息（topics + synonyms、scope、语言、tags）。"""

ask(query, mode="normal", workflow=None, kb: str | None = None) -> str
search(query, top_k=5, kb: str | None = None) -> str
```

- `kb=None` → 使用当前活动库（默认），**行为与改造前完全一致**（向后兼容）；
- `kb` 不存在 → 返回明确错误文本，不静默回退。

### 2.3 `kb_list` 输出规格

面向 agent 的自然语言，按库分组：

```
Knowledge bases (2):

## lsl-kb   [active]
   Scope: Second Life LSL — syntax, events, functions, libraries
   Topics:
     Language       : LSL Overview, LSL Events
     Reference      : LSL Functions

## eva-kb
   Scope: Evangelion 剧情与设定资料
   Topics:
     Characters     : 碇真嗣, 绫波丽
```

**L1 默认不带统计数字**（不建数据库连接）。
规模统计留作 `with_stats=True`，v0 不实现。

### 2.4 库描述的三级回退

```
1. workspace/<kb>/config/meta.yaml 的 description     ← 显式声明
2. workspace/<kb>/scope.md 第一个非空段落              ← 人写的说明
3. workspace/<kb>/config/topics.yaml 的 group 名拼接   ← 兜底
```

`meta.yaml` 结构：

```yaml
name: "armkb"                     # 必须等于目录名（不一致以目录名为准）
description: "ARM 架构与 Arm 授权 IP — Cortex-M/R/A、AMBA 总线、Ethos NPU"
language: "zh"                    # 可选
tags: ["ARM", "SoC"]              # 可选
```

### 2.5 实例可用性探测（2026-11-20 追加）

`kb_list` / `/api/kb` 按 D1 只读文件系统、不碰数据库。这对 agent 是对的，对 UI 不够：
**目录存在不代表本实例能服务它**——trial-host 上两套 compose 共用同一个 workspace 根，
但各有独立的 PostgreSQL，因此 `coffee` 栈看得见 `ai-history` 目录却连不上它的库，
切过去直接 500。

修法：

```http
GET /api/kb                  # 保持零 DB（D1）
GET /api/kb?verify=true      # 每个库执行一次 SELECT 1，结果缓存
```

```json
{
  "active": "coffee",
  "verified": true,
  "kbs": [
    {"name": "coffee", "available": true, "web_url": "http://localhost:6108"},
    {"name": "ai-history", "available": false,
     "unavailable_reason": "...database \"softwiki_ai_history\" does not exist"}
  ]
}
```

- 探测：`softwiki/kb/health.py`，超时 3s，缓存 15s（`SOFTWIKI_KB_PROBE_TTL` / `_TIMEOUT`）。
- SQLite 额外校验文件是否存在——SQLite 会自动建空文件，`SELECT 1` 会假阳性。
- `meta.yaml` 新增可选 `web_url`：该库 WebUI 的地址（端口不同栈不同）；缺省则列表可见但不可跳转。
- WebUI 的库选择器改为**数据驱动**（原来写死 `coffee:6108 / ai-history:6109` 两张卡片），
  不可用的库置灰并提示「N kb not served by this instance」。

**在一个栈里新增知识库**（无需改代码）：

```bash
mkdir -p workspace/<new-kb>/{config,.softwiki}
docker exec <stack>-postgres-1 psql -U softwiki -d postgres \
  -c "CREATE DATABASE softwiki_<new_kb> OWNER softwiki"
```

`DATABASE_URL_TEMPLATE` 的 `{workspace}` 会自动拼出新库名，`/api/kb?verify=true` 立刻可见。
2026-11-20 在 ai 栈实测通过（建 `probe-kb` → available=true → 删除）。

## 3. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| D1 | `kb_list` 默认零 DB | agent 在不知道该问哪个库时调用它；触发 DB 等于预热全部库缓存 |
| D2 | `meta.yaml` 优先，`scope.md` 次之，`topics.yaml` 兜底 | 新库往往不会写 `scope.md`，但一行 description 会随手填；三级回退保证任何库都能被描述 |
| D3 | **每库一个 PostgreSQL database**（`softwiki_<kb>`） | 现有 `DATABASE_URL_TEMPLATE` 本就按库名派生，零改动；物理隔离 = 跨库冲突误报不可能发生 |
| D4 | `set_workspace_dir` 保留但收口：请求路径不得调用；auth 关闭时 `/api/workspace` 返回 403 | 函数本身无错，错的是请求路径调用它 |
| D5 | **v0 只做单库 ask**，跨库留 v1 | 跨库有引用编号碰撞与冲突裁决两个真问题 |
| D6 | 缓存淘汰不实现，仅预留 `workspace_cache.max_loaded` 配置位 | 实测 10 库 ≈ 1GB，20 库场景不构成问题 |
| D7 | `/api/kb` 默认零 DB，`?verify=true` 才探测 | agent 要零成本列表；UI 必须知道本实例能否服务该库，否则会给出切过去 500 的选项 |
| D8 | 可用性探测带 TTL 缓存（15s）+ 3s 超时 | 每次开页面探测 N 个库会很慢；探测失败必须降级为"不可用"，不能让列表 500 |

### 不选 schema（C）的理由

C 的唯一优势是「同库内跨 schema JOIN」，但：

1. 跨库检索的融合（RRF / MMR）本来就发生在 Python 里，数据库帮不上忙；
2. C 的隔离边界是连接上的 `search_path` 字符串，漏设会**静默混库**；
   B 的隔离边界是物理独立的数据库，写错代码也不会串。
3. 更关键：C「能」做跨库冲突检测，而**跨库冲突检测本身是错的**——
   两个库对同名概念的说法可能根本不是同一件事，引擎没有依据判断。

### 跨库原则（约束 v1）

> **跨库只做叠加，不做裁决。**
> 服务端不得跨库判定冲突、不得替用户选边。
> 正确形态是「来自 A 库的 N 条 + 来自 B 库的 M 条，各自带来源」，
> 由调用方（agent / 用户）合并取舍。

推论：跨库引用必须带库名前缀（`armkb:[3]`），否则合并后不可追溯。

## 4. 实施清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `softwiki/kb/registry.py`（新） | 扫描库目录、解析 `meta.yaml` / `scope.md` / `topics.yaml`、渲染 `kb_list` / `kb_describe` |
| 2 | `softwiki/mcp/server.py` | `ask` / `search` 加 `kb` 参数；新增 `kb_list` / `kb_describe` |
| 3 | `softwiki/mcp/sse.py` | 同上（SSE / Streamable HTTP 传输） |
| 4 | `softwiki/mcp/context.py`（新） | MCP 请求级 workspace 中间件 |
| 5 | `softwiki/api/server.py` | `AskRequest` 加 `kb`；auth 关闭时 `/api/workspace` 与 `/wiki/switch` 返回 403 |
| 6 | `softwiki/source_store/db.py` | engine 改为按 DB URL 缓存的字典 + 上限 |
| 7 | `tests/test_multi_kb.py`（新） | 上述行为的测试 |

## 5. 验收

- [ ] `kb_list` 列出全部库与 topics，且**不初始化任何数据库**（日志无 `init_tables`）
- [ ] `ask(kb="A")` / `ask(kb="B")` 交替调用，答案与引用分别来自 A / B
- [ ] 不传 `kb` 时行为与改造前一致
- [ ] `kb` 不存在时返回明确错误
- [ ] auth 关闭时 `POST /api/workspace` 返回 403
- [ ] `pytest tests -q` 全绿

## 6. 已知限制

- v0 不提供跨库检索；调用方需分别 `ask` 后自行归纳（证据粒度受限于答案文本）。
- 规模统计（docs/claims 计数）需 `with_stats`，v0 未实现。
- 缓存淘汰未实现，`workspace_cache.max_loaded` 仅预留。
- 移植（`kb export` / `kb import`）不在 v0 范围；未来形态为「打包目录 + `pg_dump`」。

## 7. trial-host 现状（2026-11-20）

两套 compose 栈，**共用同一个 workspace 根**，但各有独立 PostgreSQL：

| 栈 | Web | MCP | API | PostgreSQL 内的库 |
|---|---|---|---|---|
| coffee | 6108 | 6100 | 127.0.0.1:6200 | `softwiki_coffee` |
| ai | 6109 | 6102 | 127.0.0.1:6202 | `softwiki_ai_history` |

因此：

- 两栈都能**看见**全部库目录（`/api/kb` 各返回 2 条）；
- 但只能**服务**自己 PostgreSQL 里有库的那一个（`?verify=true` 正确标出另一个不可用）；
- 每栈独立扩容：在任一栈内 `mkdir` + `CREATE DATABASE` 即可加库，已实测。

跨栈提问（6200 问 ai-history）会失败，因为 D3 的隔离边界是「每库一个 database」，
前提是**同一个 PostgreSQL 实例**。要让一个栈服务全部库，需合并两套 postgres
（或让两个 postgres 互相可达），并同时处理 Hermes（一个 MCP 而非两个）与
wikiweb（按库路径且不破坏 `kb_scope`）——独立决定，暂缓。
