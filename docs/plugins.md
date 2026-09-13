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

## UI 槽位（Cordis-lite）

前端扩展槽：`web/src/runtime/pluginSlots.ts`。完整 Cordis fiber 图仍 deferred（见 [deferred.md](./deferred.md)）。

| Slot | 用途 | 注册 API | 宿主 |
|------|------|----------|------|
| `tool.call.view` | 工具调用卡片 | `registerToolView(name, Component)` | 聊天时间线工具条 |
| `canvas.view` | Canvas 文档视图 | `registerCanvasView(kind, Component)` | `CanvasPane` |
| `composer.action` | Composer 额外动作（预留） | `registerSlot` | — |
| `dock.panel` | 右坞面板（预留） | `registerSlot` | — |

### 工具卡片

内置 `web_search`、workspace 工具、`open_canvas` 等有专用 / 共用卡片。注册入口：`web/src/components/tools/registerBuiltinTools.ts`。  
说明：[web/docs/tool-views.md](../web/docs/tool-views.md)。

### Canvas 视图

内置 kind：`mermaid` / `echarts` / `drawio` / `table` / `markdown` / `delivery`。  
注册入口：`web/src/components/canvas/registerBuiltinCanvasViews.tsx`。

```ts
import { registerCanvasView } from "@/components/canvas/canvasRegistry";

registerCanvasView("kanban", MyKanbanView);
```

Dock **插件 → 扩展槽** 可查看当前已注册的 `canvas.view` key。  
产品与 Agent 工具 `open_canvas`、落盘 `.nlm/canvases/` 详见 **[canvas.md](./canvas.md)**；前端 API 详见 [web/docs/canvas-views.md](../web/docs/canvas-views.md)。

### 本地插件市场

- API：`GET /api/plugins/marketplace`，`POST /api/plugins/install`
- `plugins_volume/**`：bundled；`plugin_catalog/**`：可安装包
- Dock：**插件 → 市场**（路径 / zip）。样例：`plugin_catalog/hello_market`

公开远程目录仍 deferred。见 [plugin-packaging.md](./plugin-packaging.md)。
