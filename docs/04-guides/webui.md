# WebUI 使用指南

## 启动

```bash
./sw api                    # REST API @ :8000
cd web && npm run dev       # 前端 @ :3000（可选）
```

`./sw api` 启动后端 API 服务，同时托管 WebUI 静态页面。访问 `http://localhost:8000` 即可使用。

如需在开发模式下运行前端（热重载），另开终端执行 `npm run dev`，访问 `http://localhost:3000`。

## 面板

### ChatPanel — 研究问答

RAG（检索增强生成）对话界面。输入研究问题后，系统跨全文搜索、向量检索、声明库和知识图谱进行检索，生成带来源引用的回答。

- **来源引用**：每条回答底部列出引用来源，点击可展开 SourceDrawer 侧边栏，查看来源元数据、相关摘要和原文链接
- **建议问题**：空对话时展示预设问题入口，一键提问
- **会话内操作**：清空对话（Clear session），Enter 发送，Shift+Enter 换行
- **状态提示**：API 不可用时显示错误指引

### IngestPanel — 来源摄入

支持两种摄入模式：

- **Web URL**：输入网页链接摄入文本内容
- **PDF 文件**：拖拽或点击上传 PDF 文件

可选 Source ID 字段匹配 `configs/sources.yaml` 中的来源配置。摄入成功后自动提取声明（claims）。

操作按钮：

- **⊕ Ingest Document**：执行摄入
- **⟳ Rebuild Index**：重建向量 + BM25 全文索引（摄入后必须执行才能搜索到新内容）

底部 Activity Log 展示所有操作的实时日志。

### DocumentsPanel — 已摄入文档

展示所有已摄入文档的表格，包含：

| 字段 | 说明 |
|------|------|
| Title | 文档标题，含原文链接（如有） |
| Source | 来源名称（如 wikipedia, reuters） |
| Type | 来源类型（web / pdf / manual） |
| Published | 发布日期 |
| Trust Level | 信任标识（high / medium / low） |
| Actions | 删除按钮（确认后级联删除关联的 chunks、claims、events、relationships） |

### ClaimsPanel — 声明与断言

展示从已摄入文档中自动提取的结构化声明表格：

| 字段 | 说明 |
|------|------|
| Actor | 声明主体（人物/组织） |
| Topic | 主题标签 |
| Stance | 立场分类：Supportive / Cautious / Opposed / Unclear |
| Confidence | 置信度百分比 |
| Claim Description | 声明原文 |
| Date | 发表日期 |

顶部提供两个筛选器：

- **Actor**：按主体筛选（下拉菜单，自动聚合所有出现的 actor）
- **Stance**：按立场筛选（Supportive / Cautious / Opposed / Unclear）

### WikiPanel — Wikipedia 风格阅读器

将知识库内容编译为结构化 Wiki 页面。

布局分为三栏：

- **左栏 Topics**：所有可用主题列表，点击切换
- **中栏 Article**：Markdown 渲染的 Wiki 正文，带内嵌目录（Contents）
- **右栏 TOC**：粘性目录边栏，滚动时自动高亮当前章节

操作：

- **◆ Compile Wiki Page**：首次编译所选主题
- **↻ Rebuild**：重新编译（数据更新后使用）
- 滚动时 IntersectionObserver 自动追踪活动章节

## 会话管理

左侧边栏 Sessions 区域：

- **创建**：点击 `+` 按钮新建会话
- **切换**：点击会话项激活
- **删除**：悬停显示 `✕` 按钮
- **重命名**：双击会话名称编辑，Enter 确认，Escape 取消
- **自动命名**：发送首条消息后自动以提问内容命名
- **持久化**：会话数据（含消息历史）自动保存至浏览器 `localStorage`

侧边栏顶部导航可在 Chat / Ingest / Documents / Claims / Wiki 五个面板间切换，Documents 和 Claims 面板旁显示计数徽章。

## 主题切换

右上角浮动按钮，依次循环切换：

Dark（🌙）→ Light（☀️）→ Auto（◐）→ Dark…

- 设置保存至 `localStorage`，刷新后保留
- Auto 模式下监听系统 `prefers-color-scheme`，实时响应系统主题变化
