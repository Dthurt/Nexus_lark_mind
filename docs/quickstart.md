# 快速开始

1. 复制环境变量：`cp .env.example .env`
2. （可选）填入模型 Key / 飞书凭证
3. `docker compose up --build -d`，或本机 `scripts\start_local.bat`
4. 打开 http://localhost:8000 开始对话

无 Key 时为 demo 回声模式，用于验证链路。

## 建议下一步

| 目标 | 文档 |
|------|------|
| 绑定本机/SSH 工作区 | [workspaces.md](./workspaces.md) |
| 计划模式 / Delivery / 审批 | [interaction-modes.md](./interaction-modes.md) |
| 聊天内 Mermaid / ECharts / Draw.io | [diagrams.md](./diagrams.md) |
| 旁侧 Canvas（编辑、Agent、落盘） | [canvas.md](./canvas.md) |
| 模型与 Provider | [model-settings.md](./model-settings.md) |
| 插件与前端槽位 | [plugins.md](./plugins.md) |
| 工作台布局 | [client-architecture.md](./client-architecture.md) |

更完整的架构说明：[architecture.md](./architecture.md)。本地开发细节：[local-start.md](./local-start.md)。
