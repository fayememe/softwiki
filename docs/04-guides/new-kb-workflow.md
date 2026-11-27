# 新建知识库 → 加资料 → 可问答（操作手册）

> 状态：✅ 与 2026-11-26 的实现一致（建库自动建数据库、批量导入、按库 Wiki 门户）
> 适用：单实例 WebUI（javis 6108 / trial coffee 6108、ai 6109）

整个流程分 7 步，其中 **3 处需要等**、**2 处需要注意代价**，都标出来了。

> 随时可以打开侧栏 **资料流程** 看每一环的状态：是否需要更新、是否正在生成、以及它们之间
> 谁依赖谁（检索链路 / 知识链路 / 发布链路三条并列显示）。

---

## 0. 先确认在哪台机器/哪个库

左上角下拉是「知识库」，下面是「角色」。切换库会记住在你的账号上（单机 `off` 模式即本机）。
切换后页面会重载，所有面板都跟着换库。

---

## 1. 建库（WebUI）

**Management → Knowledge bases（知识库管理）**

1. 填名称：只允许字母、数字、点、横线、下划线；**同时是目录名和数据库名后缀**
2. 选模板：`generic` / `research-report` / `course-qa`
3. 填描述（会出现在 `kb_describe`、首页卡片里；留空则回退 `scope.md`）
4. **预览计划** → 确认文件清单 → **创建**

创建会做三件事：

| 动作 | 结果 |
|---|---|
| 建目录 | `<WORKSPACES_ROOT>/<kb>/{config,raw,.softwiki}` |
| 写配置 | `config/meta.yaml`、`config/topics.yaml`、`scope.md` |
| **建数据库** | PostgreSQL：`CREATE DATABASE softwiki_<kb>`（SQLite 则建文件），并建表 |

> 若第 3 步失败，页面会报「数据库创建失败：…」。该库会显示 `UNAVAILABLE`，
> 可在同一面板该行点「创建数据库」重试（幂等）。**老库没有数据库时也用它补。**

建完侧栏下拉会**自动出现**该库，不用刷新页面。

---

### 1.1 模型配置（重要）

新库默认继承部署的 `config/model_profiles.yaml`（由 `SOFTWIKI_KB_MODEL_PROFILES` 指定）。
若该变量没设置，新库会回落到 `.env` 的默认 provider —— 曾经因此落到欠费的 Gemini，
表现为抽取/wiki 生成 `Error code: 402`。

排查：`kb/config/model_profiles.yaml` 是否存在；`pipeline_status` 里的 claims/wiki 是否一直是 0。

## 2. 切到新库

侧栏「知识库」下拉选中新库 → 页面重载。

此时：

- 首页「总览」里该库是 `CURRENT`，文档 0
- 文档 / 论断 / 图谱 / 时间线都是空

---

## 3. 加资料（推荐：批量拖 PDF）

**Ingest（导入）→ PDF 文件**

- 把多个 PDF **一次拖进虚线框**（或点击多选），它们会进上传队列
- 队列**串行**上传：一条 `上传中`，其余 `等待`；可以继续拖，追加到队尾
- 每行会变成 `完成` / `跳过` / `失败`；失败可「重试」，也可「重试失败项」
- 跳过通常是：**内容去重**（同 hash 已存在）或 **scope guard 判为越界**

其他来源：

| 来源 | 入口 | 说明 |
|---|---|---|
| 网页 | 导入 → 网页链接 | 需要目标机可出网；trial-host 对部分站点被墙 |
| Markdown | 导入 → PDF 文件（可传 `.md`） | 支持 front matter：`title/author/date/url`，**没有页码** |
| 脚本批量 | `scripts/ingest_pdf_batch.py` | 走同一 `/api/ingest/file`；注意它按 SQLite 路径统计进度，PG 部署下统计不准 |

文件落盘在 `<workspace>/raw/pdf/<文件名>`。

---

## 4. 等抽取（后台，和上传不是一件事）

每个文档上传成功后，后端在后台跑 `run_extraction_pipeline`：

- ClaimDB（论断）
- 实体 / 关系（图谱）
- 事件（时间线）

**上传完成 ≠ 抽取完成。** 判断方式：

- 首页「总览」该库的 `论断 / 实体 / 关系 / 事件` 计数在涨
- 或「论断」面板能看到新内容

大 PDF 可能要几分钟到十几分钟。若 LLM 供应商故障，抽取会停在 pending；
此时看 `GET /api/knowledge/metrics` 的 `llm_provider`（`open` / `retry_in`）。

---

## 5. 建索引（必须手动点一次）⚠️

**导入 → 重建索引**（`POST /api/index`）

这一步才产生 **chunk + 向量 + BM25**；只导入不建索引，`/api/ask` 检索不到新文档。

⚠️ **当前是全量重建**：会删掉重建**所有文档**的 chunk 并重新 embedding。
小库几秒到几十秒；几十万 chunk 的库会明显耗时间和 embedding 额度。
只加了几篇也建议在维护窗口做，或者等后续做增量索引。

---

## 6. 验证能问答

- 侧栏 → 对话（默认 SWAgent），问一个只有新资料才有答案的问题
- 或 `POST /api/ask`，看 `sources` 是否带页码/文档名

若答案空/不带引用：回到第 5 步确认 `vector_index` / `bm25_index` 是否为 true。

---

## 7. 生成 Wiki 页面 + 静态门户

**Wiki portal → 页面与生成**

1. 选择主题或点生成，产出「一实体一页」的 wiki 页面（会有队列，慢慢跑）
2. 生成后用 `GET /api/wiki/pages` 确认 `generated: true`，右侧栏状态会显示主题页数量

**静态门户**：目前只有脚本（面板里的「重建门户」按钮是灰的）：

```bash
# 在部署机执行（kb 换成你的库名）
python scripts/wikiweb_build.py --kb <kb> \
  --workspace /data/workspaces/<kb> \
  --limit 300 --min-claims 3 \
  --prose-dir /data/workspaces/<kb>/exports/wiki/pages
```

生成后**刷新页面即可**（2026-11-26 起 `/wikiweb/<kb>/` 每次请求读盘，不再需要重启 web）。
没生成门户的库会显示「No static portal has been generated…」，不会串到别的库。

---

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 新库在下拉里灰着 | 数据库没建成 → 知识库管理里点「创建数据库」 |
| 拖进去显示「跳过」 | 内容重复 或 越界；越界需改该库 `scope.md` / `config/scope` |
| 导入成功但问不到 | 忘了第 5 步「重建索引」 |
| 论断一直是 0 | 后台抽取未完成或 LLM 熔断；看 `/api/knowledge/metrics` |
| 门户还是旧的 | 重新跑 `wikiweb_build.py` 后刷新；门户是静态快照，不随 claim 自动更新 |
| 首页看不到该库 | 该库不在本实例（trial 两栈各只挂自己的 workspace 根） |
