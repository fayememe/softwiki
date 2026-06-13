# QuickStart

## 1. Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev,graph]"
cp .env.example .env
# Edit .env to fill in API keys
```

## 2. Initialize

```bash
./sw init
```

## 3. Ingest

```bash
./sw ingest --url "https://example.com/article"
# Or import the EVA sample data
python scripts/seed_eva.py
```

## 4. Ask Questions

```bash
./sw ask "What is the Human Instrumentality Project?"
```

## 5. Launch Shell / WebUI

```bash
./sw shell     # TUI (requires opencode)
./sw api       # REST API + WebUI
```

## Register MCP Server

Add to your AI tool's MCP configuration (Claude Desktop / Cursor / opencode):

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
