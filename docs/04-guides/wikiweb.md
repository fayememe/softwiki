# Wikiweb（静态门户）构建指南

> 入口（javis）：`http://10.3.9.29:6108/wikiweb/armkb/index.html`
> 生成器：`scripts/wikiweb_build.py` ｜ 模板：`softwiki/templates/wikiweb/`

## 它是什么

Wikiweb 是**发布层**：把知识库渲染成静态 HTML 站点（主页/分类/时间线/实体页/搜索）。
它和 LLM Wiki 不是一回事：

| | LLM Wiki | Wikiweb |
|---|---|---|
| 内容 | 生成的页面正文（markdown/工件） | 发布出去的 HTML |
| 位置 | `<kb>/exports/wiki/pages/` | `<kb>/exports/wikiweb/` |
| 消费者 | WebUI 的 LLM Wiki 面板 | 浏览器 `/wikiweb/` |

## 生成

```bash
# 在 api 容器内（有 DB + workspace）
python /app/scripts/wikiweb_build.py \
  --out-root /data/workspaces/armkb/exports/wikiweb \
  --kb-dir armkb --kb-label ARM \
  --description "ARM architecture and IP documentation: ..." \
  --limit 300 --min-claims 3 \
  --prose-dir /data/workspaces/armkb/exports/wiki/pages
```

- 事实：canonical claims（active/disputed）+ 页码引用；
- 时间线：events；
- 连接：relationships（按 relation_type 分组，weight = 跨文档数）；
- 参考：documents（标题/域名/日期/链接）；
- 摘要：优先取 LLM Wiki 页首段，没有就用 claims 拼句（**不调 LLM**）；
- 只链接到实际生成的页面；slug 冲突自动加 `-2` 后缀。

输出结构（由 `/wikiweb/<kb>/...` 直接读盘提供）：

```
exports/wikiweb/
  assets/wiki.css, wiki.js
  armkb/index.html all.html timeline.html about.html search-index.json
  armkb/category/<type>.html
  armkb/wiki/<slug>.html
```

## 更新内容、不改框架

- 生成器复用同一份 `assets/` 与外壳（header/sidebar/nav），重跑只替换 `main` 内容与索引；
- 框架稳定性可验证：对比生成前后的 `assets/` 和外壳 hash（脚本固定模板）；
- 新实体：重新生成会新增页面；被淘汰的实体页面不会自动删除，需要手工清理。

## 不再需要重启 web 容器

2026-11-26 起，`/wikiweb` 由 `app/wikiweb/[...path]/route.ts` **每次请求读盘**，直接取
`<stack>/<kb>/exports/wikiweb/` 下的文件：

```
/wikiweb/<kb>/...   -> <stack>/<kb>/exports/wikiweb/<kb>/...
/wikiweb/<kb>/assets/... -> <stack>/<kb>/exports/wikiweb/assets/...
/wikiweb            -> 307 到当前 active kb
```

- 重新生成门户后**刷新页面即可**，不用 `docker restart`（旧实现把单库导出目录挂到
  `public/wikiweb` 并固定 `WIKIWEB_ENTRY`，既要求重启，又让所有库都显示同一个门户）；
- web 容器只需要把 `SOFTWIKI_STACK_ROOT` 只读挂到 `/data/workspaces`；
- 该库没生成门户时返回明确的提示页，而不是别的库的内容。

否则 `/wikiweb/...` 返回 404（文件确实在容器里，但 Next 不认识）。

## 当前部署

| 环境 | 门户 | 说明 |
|---|---|---|
| javis armkb | ✅ 300 页，12 分类 | 2026-11-25 生成，`/wikiweb/armkb/` 200 |
| trial coffee | 用户 agent 生成的原版 | **不要覆盖**；如需替换先备份 |
| trial ai-history | 同上 | — |

## 限制

- 静态快照：数据变了要重跑生成器（或接 worker/timer）；
- 摘要来自 LLM Wiki 页，页面未重建时摘要可能滞后；
- 只生成 top-N 实体（默认 300，`claims>=3`），不是全量 9k 实体；
- 搜索是前端 `search-index.json` 子串匹配，不是全文索引。
