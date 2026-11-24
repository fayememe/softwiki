# Graph Studio 使用指南

> 入口：`http://<host>:6108/graph-studio`（侧栏 **Graph Studio ↗**）
> 数据：`/api/graph/*`；检索层：`softwiki/intelligence/graph_claim.py`

## 用途

给演示 / 排查准备的图谱工作台，不需要登录，直接可投屏。

- **搜索**：输入实体名（或别名，如 `M55`），下拉来自 `/api/graph/search`；
- **画布**：初始加载 `/api/graph/overview` 中度数最高的实体；单击节点看详情，
  双击展开一跳邻居（`/api/graph/subgraph`），拖拽平移、滚轮缩放；
- **路径**：填 from / to，点 **Find path**，走 `/api/graph/path`（最多 3 跳），
  命中的边和节点用金色高亮；
- **实体卡**：名称/类型/描述、别名、度数、最强关系（按 `weight` 排序）、
  关联 canonical claims（状态/证据数/页码）、已编译 wiki 摘要。

## 数据语义

| 元素 | 含义 |
|---|---|
| 节点颜色 | 实体类型（product / protocol / register / feature …） |
| 边粗细 | `log(1 + weight)`，`weight` = 跨文档出现的**不同文档数** |
| 边背后的 claim | `relationships.canonical_claim_id` → `canonical_claims` |
| 别名 | `entity_aliases`（抽取 aliases + 同名合并产生的旧名） |

## 常见操作

```bash
# 重新归一实体 / 重算边权重（不删行）
docker exec softwiki-api-1 python scripts/graph_normalize.py

# 某个实体的原始 JSON
curl 'http://127.0.0.1:6200/api/graph/entity?name=Cortex-M55' | jq .

# 两实体最短路径
curl 'http://127.0.0.1:6200/api/graph/path?source=Cortex-M55&target=Helium&max_hops=2' | jq .

# 验收 + 延迟
docker exec softwiki-api-1 python scripts/graph_acceptance.py --runs 5
```

## 已知限制

- 实体链接是确定性的（归一化 + 别名 + 度数），不做向量召回；
- 边端点在归一后仍有少量未解析（抽取名称与实体表不一致），详情卡会显示但
  不参与路径计算；
- `weight` 只统计 distinct 文档，不衡量语义质量；`confidence` 来自抽取模型。
