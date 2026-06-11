# QuickStart

## 1. 安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev,graph]"
cp .env.example .env
# 编辑 .env 填入 API key
```

## 2. 初始化

```bash
./sw init
```

## 3. 摄入

```bash
./sw ingest --url "https://example.com/article"
# 或导入 EVA 示例数据
python scripts/seed_eva.py
```

## 4. 问答

```bash
./sw ask "What is the Human Instrumentality Project?"
```

## 5. 启动 Shell / WebUI

```bash
./sw shell     # TUI（需 opencode）
./sw api       # REST API + WebUI
```

## 注册 MCP Server

在 Claude Desktop / Cursor / opencode 等 AI 工具的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "softwiki": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "softwiki.mcp.server"],
      "cwd": "/path/to/softwiki",
      "env": {
        "WORKSPACE_DIR": "/path/to/your/workspace",
        "PYTHONPATH": "/path/to/softwiki"
      }
    }
  }
}
```
