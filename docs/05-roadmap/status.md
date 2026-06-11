# 项目状态

## Phase 1 — 核心知识引擎

- ✅ 文档摄入 — URL + PDF，SHA-256 去重，多语言
- ✅ 五层知识抽取 — Claim / Entity-Relationship / Timeline / RAG / LLM-Wiki
- ✅ 混合检索 — dense + BM25，RRF 融合
- ✅ RAG 问答引擎 — 5 层上下文融合，引用管理
- ✅ MCP 服务基础 — 17 tools，stderr 保护 JSON-RPC
- ✅ CLI — init/ingest/index/ask/wiki/shell/api
- ✅ Shell TUI — opencode wrapper，零 core 依赖
- ✅ 工作空间隔离 — WORKSPACE_DIR 任意路径，完全独立
- ✅ Scope 约束 — scope.md 驱动知识库范围检查

## Phase 2 — 图增强 + WebUI

- ✅ LightRAG 集成 — BFS 遍历，6 种查询模式，增量插入
- ✅ 存储后端抽象 — JSON / PostgreSQL 配置切换
- ✅ LLM/Embedding 分离 — 不同 Provider 独立设置
- ✅ 维度安全检测 — embedding 模型变更时自动拦截
- ✅ WebUI 重设计 — 暗色主题，Plus Jakarta Sans 字体
- ✅ 会话管理 — 创建/切换/删除/重命名，localStorage 持久化
- ✅ Wikipedia 阅读器 — Linux Libertine 字体，TOC 边栏
- ✅ 主题切换 — Dark / Light / Auto 循环
- ✅ MCP 工具扩增 — 17 tools（+lightrag_query/explore/status）
- ✅ 架构文档整理 — 18 文档六层分类

## Phase 3 — 远程访问

- ☐ 远程 MCP — HTTPS + Bearer token
- ☐ swshell 独立客户端 — 零 core 依赖，HTTP MCP 连远端
- ☐ index() 增量模式 — 全量重建→只处理新增文档

## Phase 4 — 权限与多用户

- ☐ Token/RBAC — 正式 token 机制绑定 role + workspace
- ☐ wiki-work submit 流程 — staging → review → publish
- ☐ 审计日志 — MCP 操作可追溯

## Phase 5 — 部署与质量

- ☐ WebUI 响应式 — 移动端适配
- ☐ web_loader 升级 — Readability.js / Jina AI Reader
- ☐ 测试覆盖 — extraction / wiki / answer_engine
- ☐ Docker 部署栈 — docker-compose 一键启动
