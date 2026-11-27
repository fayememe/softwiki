# 事故记录：后台抽取写错知识库（2026-11-26）

> 影响库：`armkb`（javis） · 修复版本：`250f2f6` / `5f8aadc` · 数据恢复完成

## 1. 现象

第一次给新库 `tsmckb` 跑「继续抽取」后：

- `tsmckb` 文档一直 `pending`，claims 0；
- `armkb` 的 claims 从 **15,465** 涨到 **21,649**，entities 9,256 → 9,704，
  relationships 9,491 → 10,248，events 743 → 1,025；
- `armkb` 有 8 篇文档变成 `failed`、2 篇卡在 `extracting`（原本全部 completed）；
- claim 变化触发 wiki 自动重建，armkb 出现 109 个 pending + 3 个 running 任务，
  开始用污染数据重写页面。

## 2. 根因（两个，叠加）

1. **后台线程没有继承请求的 kb**
   `run_extraction_pipeline(background=True)` 里 `threading.Thread` 不继承请求的
   ContextVar；worker 里 `SessionLocal()` 调用 `get_db_url()` 时拿不到 kb，
   回退到进程环境默认库（`WORKSPACE_DIR=armkb`）。
   结果：用 tsmckb 请求里捕获的正文，往 armkb 的 doc id 上写 claims。

2. **并行 canonicalize**
   同一批 10 篇同时调用 `canonicalize_document`，在 `canonical_claims` 上互相死锁，
   或插入同一个主键（`cc_...` 全局唯一）。失败后事务回滚，文档状态停在 pending。
   项目里早有「并行抽取 → 串行 canonicalize」的约定，但代码里没有锁。

## 3. 修复

| 提交 | 内容 |
|---|---|
| `250f2f6` | `_bg_extraction_worker(..., kb)`，线程内 `enter_kb(kb)`；`run_extraction_pipeline` 捕获 `current_kb_name()` 传入；`canonicalize_document` 加全局锁 |
| `5f8aadc` | wiki 重建 worker 同样没有 kb 上下文，过去只处理默认库；改为按 kb 轮转（启动恢复 / 任务循环 / reconcile 都遍历，定期重新发现新库） |
| `250f2f6` | `extract-pending` 只挑没有 claims 的文档，避免重复追加断言 |
| `5f8aadc` | `/api/index` 完成后清 pipeline 缓存 |

回归测试：

- `tests/test_extraction_kb_context.py`：worker 进入指定 kb、pipeline 把 kb 传给线程、规范化锁存在；
- `tests/test_wiki_worker_kbs.py`：worker 轮转 kb、kb 发现失败时回退默认库。

## 4. 数据恢复（armkb）

备份：`backup-armkb-before-pgvector-20261124-192809.sql.gz`（污染前，claims 15,465）。

步骤：

1. 停 `softwiki-web-1 / softwiki-mcp-1 / softwiki-api-1`；
2. `CREATE DATABASE softwiki_armkb_restore`，用 `pg_dump` 备份灌入；
3. 校验：73 docs / 15,465 claims / 14,704 canonical / 9,256 entities / 9,491 rels / 743 events；
4. `ALTER DATABASE` 把原库改名 `softwiki_armkb_bad_20261127`（保留取证），restore 库改名为 `softwiki_armkb`；
5. 启动容器；
6. 重灌向量：`python scripts/migrate_vectors_to_pg.py --batch 500` → 39,870 live / 39,870 孤儿丢弃 / HNSW；
7. 校验 `/api/ask`（11 sources，带页码）与 `/api/kb/pipeline`。

回滚用的坏库 `softwiki_armkb_bad_20261127` 仍在，确认无误后可删除。

## 5. 验证（恢复后）

```
armkb  docs 73 completed · chunks 39,870 · vectors 39,870
       claims 15,465 / canonical 14,704 / disputed 34
       entities 9,256 / rels 9,491 / events 743
       wiki 542 subject pages · portal 617 pages
```

端到端（tsmckb）：

1. 上传 `TSMC N3` 测试文档 → extraction 落到 **tsmckb**（armkb 保持 15,465）；
2. 批量补抽其余 14 篇 → 16/16 completed、claims 5,650、canonical 4,628；
3. `POST /api/index` → 1,793 chunks / vectors / BM25，`/api/ask` 命中新文档（9 sources）；
4. 投影回填：relationships 未挂 claim 267 → 4，events 146 → 44；
5. wiki worker 已经开始处理 tsmckb 的任务（过去永远不会）。

## 6. 仍未做（已知缺口）

- **投影（claims → edges/events）没有接进流程**，仍是手工脚本；
- 索引仍是全量重建；
- 文档列表不显示抽取状态，只能靠「资料流程」看计数；
- trial-host 未更新到本轮代码。
