# Shell 搜索配置

sw shell 默认使用 **DuckDuckGo** 进行网络搜索，无需任何 API key，开箱即用。

如需更好的搜索质量或更高的请求限额，可以配置以下任一搜索服务。

---

## 配置方法

在工作目录的 `.env` 文件中添加对应的 API key，重启 shell 即可生效。

### Exa（推荐，AI 原生）

```bash
EXA_API_KEY=your_key_here
```

注册地址：https://exa.ai — 免费额度 1000 次/月

### Tavily（适合研究场景）

```bash
TAVILY_API_KEY=tvly-your_key_here
```

注册地址：https://tavily.com — 免费额度 1000 次/月

---

## 配置自定义搜索 MCP

如需接入其他搜索服务（Bing、Google、SerpAPI 等），可以在工作空间的 `config/shell-mcp.yaml` 里配置，然后让 AI 帮你写具体的配置内容：

```
告诉 sw shell：帮我配置 Bing 搜索 MCP，我的 key 是 xxx
```

shell 本身就可以帮你写配置文件。
