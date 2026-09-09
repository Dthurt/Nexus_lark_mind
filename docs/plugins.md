# 插件开发指南

## 概念

| 字段 | 含义 |
|------|------|
| `enabled` | 用户意图：是否希望该插件进入运行态（持久化到 `data/plugin_prefs.json`） |
| `state` | 运行态：`init` / `ready` / `disabled` / `error` / `teardown` |
| `health` | 含 `status`、`last_ready_at`、`last_teardown_at` |
| `config_hints` | 配置提示（如未设置 `TAVILY_API_KEY`） |
| 模型可见工具 | 仅 `state == ready` 的插件工具会进入 `as_openai_tools()` |

禁用会 **teardown** 运行时资源（如 MCP stdio 子进程），不只是改状态。  
进行中的 `invoke` 期间禁止 `reload`（返回错误）。

## CLI 插件

1. 在 `plugins_volume/cli/` 新建脚本，例如 `weather.py`
2. 从 stdin 读 JSON，向 stdout 写 JSON
3. 重启 Kernel，或调用 reload API：

```bash
curl -X POST http://127.0.0.1:8000/api/plugins/reload
curl -X POST http://127.0.0.1:8000/api/plugins/cli.weather/reload
```

## MCP Stdio / HTTP

见 `plugins_volume/mcp/*.json`。

## Web / RPC API

```bash
# 列表（version / enabled / state / health / config_hints / tools schema）
curl http://127.0.0.1:8000/api/plugins
curl http://127.0.0.1:8000/api/tools

# 启停（写入 prefs）
curl -X POST http://127.0.0.1:8000/api/plugins/builtin.echo/disable
curl -X POST http://127.0.0.1:8000/api/plugins/builtin.echo/enable

# 热重载
curl -X POST http://127.0.0.1:8000/api/plugins/reload

# 停止生成
curl -X POST http://127.0.0.1:8000/api/chat/{task_id}/cancel
curl -X POST http://127.0.0.1:8000/api/sessions/{session_id}/cancel

# 会话工具审计
curl "http://127.0.0.1:8000/api/sessions/{session_id}/plugin-calls?limit=40"
```

## 持久化

`data/plugin_prefs.json`：

```json
{ "enabled": { "builtin.echo": true, "cli.web_search": false } }
```

## UI 槽位

`@nlm/ui` → `uiSlots` / `SlotNames.TOOL_CALL_VIEW`（keyed）。  
内置 `web_search` / `cli_web_search_web_search` → 搜索结果卡片。
