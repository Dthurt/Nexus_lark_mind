# Channels — Nexus Lark Mind

## Product

**Nexus Lark Mind** 通过 Channel 接入外部 IM / 应用。当前内置：

| Channel | 说明 |
|---------|------|
| Web | 浏览器对话（始终可用） |
| 飞书 | 填入开放平台 **App ID / App Secret** 后接入本体系 |

凭证优先来自设置页（`data/channels.json`）；未配置时回退 `.env` 的 `FEISHU_*`。

## UI

**设置 → 通道**：

1. 填写飞书 App ID、App Secret（可选 Verification Token / Encrypt Key）
2. **测试连通性** — 请求 `tenant_access_token`
3. **保存并接入** — 写入本地配置并重载长连接
4. **重载长连接** — 不改凭证仅重启 WS

## API

```bash
GET  /api/settings/channels
PUT  /api/settings/channels/feishu
POST /api/settings/channels/feishu/test
POST /api/settings/channels/feishu/reload
```

飞书 body 示例：

```json
{
  "enabled": true,
  "display_name": "飞书",
  "app_id": "cli_xxx",
  "app_secret": "xxx",
  "verification_token": "",
  "encrypt_key": "",
  "use_long_connection": true
}
```

`app_secret` / token / encrypt_key 留空表示保留已存值。

## Model connectivity

设置 → 模型中的 **测试连通性**：

```bash
POST /api/settings/models/test
```

对 OpenAI-compat 端点：先 `GET /models`，再可选发一条极短 `chat/completions`。
