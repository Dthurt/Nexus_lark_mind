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

| 类型 | 卡片 | 用途 |
|------|------|------|
| `thinking` | 思考过程 | `collapsible_panel` 折叠推理 / 工具轨迹；生成中默认展开，完成后折叠 |
| `answer` | 对话 / 知识库 | 最终 markdown + 引用；有 `citations_md` 时改用青绿「知识库」头 |
| `select` | 选择 | `select_static` 选 Provider / 模型 / 权限预设 / 本地知识库；选项过多时不再铺 6 个按钮 |
| `stats` / `chart` | 统计图 | `chart` + VChart spec（由小型 ECharts option 转换）；失败时退化为指标列 |
| `error` / `confirm` | 错误 / 确认 | 红/黄错误卡去 traceback；审批与确认带 note |

流式：同一条消息 `PATCH` 更新，delta **防抖**（约 450ms）。完成后折叠思考过程，突出答案。`kb_stats` / `kb_sync_docs` 会再发一张小统计卡（本地数据，不请求 WeKnora）。

回复卡按钮：再问一次、清空会话（二次确认）。模型 / 预设 / 知识库走「会话设置」下拉。命令：`切换模型`、`权限预设`、`切换知识库`。

`/知识库`（及同义命令）打开绑定卡时会 `GET /rpc/knowledge/weknora/kbs`，把远程库填进 `select_static`（最多约 20 个，与 Web 知识库页同源）。WeKnora 未配置或失败时卡片仍可切回本地，并写明离线原因，不阻塞。选中后走现有 `pick_kb` → `weknora_kb_id` / `clear_weknora_kb_id`。

限制（开放平台）：交互卡片 JSON 约 **30 KB**、markdown 子集、更新接口有 QPS 限制。超长正文会被截断。图表走 `chart` + VChart（不是浏览器 ECharts）；旧客户端或超大 spec 退化为列指标。`collapsible_panel` 内不能嵌 form。`select_static` 的选项 `value` 必须是字符串，真实选项在回调的 `action.option`。

## Env fallback

见 `.env.example`：`FEISHU_*`、`DINGTALK_*`、`WECOM_*`。

## Model connectivity

设置 → 模型中的 **测试连通性**：

```bash
POST /api/settings/models/test
```
