# 快速开始

## 本机最快路径（推荐）

1. 复制环境变量：`Copy-Item .env.example .env`（可选填模型 Key）
2. 启动：

```bat
scripts\start_local.bat
```

3. 打开 http://127.0.0.1:8000

无 Key 时为 demo 回声模式，用于验证链路。

### 改前端时

```bat
scripts\dev.bat
```

打开 http://127.0.0.1:5173（Vite 热更新）。细节见 [local-start.md](./local-start.md)。

### Docker

```bash
docker compose up --build -d
```

打开 http://localhost:8000

## 建议下一步

| 目标 | 文档 |
|------|------|
| 本地部署 / 调试流程 | [local-start.md](./local-start.md) |
| 绑定本机/SSH 工作区 | [workspaces.md](./workspaces.md) |
| 计划模式 / Delivery / 审批 | [interaction-modes.md](./interaction-modes.md) |
| 聊天内 Mermaid / ECharts / Draw.io | [diagrams.md](./diagrams.md) |
| 旁侧 Canvas（编辑、Agent、落盘） | [canvas.md](./canvas.md) |
| 模型与 Provider | [model-settings.md](./model-settings.md) |
| 插件与前端槽位 | [plugins.md](./plugins.md) |
| 工作台布局 | [client-architecture.md](./client-architecture.md) |

更完整的架构说明：[architecture.md](./architecture.md)。
