# 插件开发指南

## CLI 插件

1. 在 `plugins_volume/cli/` 新建脚本，例如 `weather.py`
2. 从 stdin 读 JSON，向 stdout 写 JSON
3. 重启 `core-kernel`（或调用 load RPC）即可使用

## MCP Stdio

在 `plugins_volume/mcp/xxx.json` 配置 `kind: mcp_stdio` 与 `command/args`。

## MCP HTTP

配置 `kind: mcp_http` 与 `url` / `rpc_path`。

## 热插拔 RPC

```bash
curl -X POST http://localhost:8001/rpc/plugins/disable -H 'Content-Type: application/json' -d '{"plugin_id":"builtin.echo"}'
curl -X POST http://localhost:8001/rpc/plugins/enable -H 'Content-Type: application/json' -d '{"plugin_id":"builtin.echo"}'
```
