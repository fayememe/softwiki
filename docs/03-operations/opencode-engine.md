# opencode engine（SoftWiki Agent）

> SoftWiki Agent 使用 pinned opencode engine；不依赖宿主 PATH 的“随手升级”。

## 当前 pin

```text
opencode 1.19.5
/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode
```

## 为什么内置

- 宿主升级 opencode 不影响产品
- 版本可复现
- 数据/配置隔离在 `.softwiki_runtime`
- 产品名仍是 **SoftWiki Agent**；opencode 只是内部 engine

## 安装

```bash
scripts/install-opencode.sh 1.19.5 x64
```

安装到：

```text
/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode
```

## systemd

`deploy/softwiki-agent-web.service`：

```ini
Environment=SOFTWIKI_OPENCODE_BIN=/opt/aitools/apps/softwiki/engine/opencode/1.19.5/opencode
Environment=SOFTWIKI_OPENCODE_EXPECTED_VERSION=1.19.5
```

启动时会校验 `--version`；不匹配直接失败，不静默 fallback。

## 升级

```bash
scripts/install-opencode.sh 1.20.0 x64
# 改 service 的 BIN / EXPECTED_VERSION
sudo systemctl daemon-reload
sudo systemctl restart softwiki-agent-web
```

先跑：

```bash
curl -s http://127.0.0.1:6200/api/agent/status
```

## 回滚

保留上一版本目录，例如 `1.18.35`，把 service 改回：

```ini
Environment=SOFTWIKI_OPENCODE_BIN=/opt/aitools/apps/softwiki/engine/opencode/1.18.35/opencode
Environment=SOFTWIKI_OPENCODE_EXPECTED_VERSION=1.18.35
```

## 注意

- 不把二进制提交到 git
- 不暴露 6111 的 opencode UI 给最终用户；用户走 SoftWiki ChatPanel
- 个人 opencode 与 SoftWiki Agent 使用不同 XDG 数据目录
