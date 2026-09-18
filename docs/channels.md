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

## 飞书卡片（Card JSON 2.0）

对话与交互走官方 **interactive / Card Kit schema 2.0**（`schema: "2.0"`，正文在 `body.elements`，按钮 `behaviors.callback`）：

| 卡片 | 用途 |
|------|------|
| 生成中 | 同一条消息 `PATCH` 更新；工具进度 / 状态 / 引用写在卡片内，流式 delta **防抖**（约 450ms）避免触达更新频控 |
| 对话 / 知识库 | 最终回复；有 `citations_md` 时改用青绿「知识库」头 |
| 工具审批 / 询问 / 计划审阅 | 独立交互卡，回调进 Kernel `/rpc/gates/resolve` |
| 错误 / 限流 | 红色或黄色卡，去掉 traceback；可「再问一次」 |
| Provider / 模型 | 会话首次绑定；回复卡上也可「切换模型」 |

按钮：再问一次（重提原文）、切换模型、清空会话（二次确认）。不另发一堆碎消息。

限制（开放平台）：交互卡片 JSON 约 **30 KB**、markdown 子集、更新接口有 QPS 限制。超长正文会被截断；图表未使用。

## Env fallback

见 `.env.example`：`FEISHU_*`、`DINGTALK_*`、`WECOM_*`。

## Model connectivity

设置 → 模型中的 **测试连通性**：

```bash
POST /api/settings/models/test
```
