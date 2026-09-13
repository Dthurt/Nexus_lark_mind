# Channels — Nexus Lark Mind

## Product

**Nexus Lark Mind** 通过统一 Channel Hub 接入外部 IM / 应用。当前内置：

| Channel | 说明 | Webhook |
|---------|------|---------|
| Web | 浏览器对话（始终可用） | — |
| 飞书 | 开放平台 App ID / Secret；推荐长连接 | `/feishu/webhook` |
| 钉钉 | Client ID / Secret；机器人 HTTP 回调 | `/dingtalk/webhook` |
| 企业微信 | CorpID / AgentId / Secret | `/wecom/webhook` |

凭证优先来自设置页（`data/channels.json`）；未配置时回退 `.env`。

运行时所有通道经 `ChannelHub` 订阅同一 Redis 事件总线，按 `channel` 字段隔离投递。

## UI

**设置 → 通道**：

1. 概览卡片（含各通道 Logo）查看接入状态
2. 填写对应凭证 → **测试连通性** → **保存并接入**
3. 飞书可 **重载长连接**；钉钉 / 企微 **重载凭证**

## API

```bash
GET  /api/settings/channels
PUT  /api/settings/channels/feishu|dingtalk|wecom
POST /api/settings/channels/feishu|dingtalk|wecom/test
POST /api/settings/channels/feishu|dingtalk|wecom/reload
```

### 飞书

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

### 钉钉

```json
{
  "enabled": true,
  "display_name": "钉钉",
  "client_id": "dingxxx",
  "client_secret": "xxx",
  "robot_code": "",
  "token": "",
  "encoding_aes_key": ""
}
```

### 企业微信

```json
{
  "enabled": true,
  "display_name": "企业微信",
  "corp_id": "wwxxx",
  "agent_id": "1000002",
  "secret": "xxx",
  "token": "",
  "encoding_aes_key": ""
}
```

密钥字段留空表示保留已存值。

## Env fallback

见 `.env.example`：`FEISHU_*`、`DINGTALK_*`、`WECOM_*`。

## Model connectivity

设置 → 模型中的 **测试连通性**：

```bash
POST /api/settings/models/test
```
