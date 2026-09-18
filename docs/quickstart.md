# 快速开始

需要 **Python 3.11–3.13**。没有解释器（或只有 Windows 商店占位）时，`nlm` 会停住并给出自动安装 / 打开下载页 / 退出，不会一闪就关。

## 本机最快路径（推荐）

1. 复制环境变量：`Copy-Item .env.example .env`（可选填模型 Key）
2. 启动：

```bat
nlm start
```

Linux / macOS：`chmod +x nlm && ./nlm start`

3. 打开 http://127.0.0.1:8000 ，绑定工作区，即可对话。

无 Key 时为 demo 回声模式，用于验证链路。

顶栏 **知识库**：选「本地知识库」或 WeKnora 库，左边检索、右边针对该库提问。主输入框也有知识库选择器。详见 [knowledge-base.md](./knowledge-base.md)。

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
| 本地部署 / 缺 Python / 调试 | [local-start.md](./local-start.md) |
| 知识库检索 + 针对某库对话 | [knowledge-base.md](./knowledge-base.md) |
| 飞书卡片 / 通道 | [channels.md](./channels.md) |
| Skills / 扩展 / 预设 | [pi-inspired-extensions.md](./pi-inspired-extensions.md) |
| 绑定本机/SSH 工作区 | [workspaces.md](./workspaces.md) |
| 计划模式 / Delivery / 审批 | [interaction-modes.md](./interaction-modes.md) |
| 聊天内 Mermaid / ECharts / Draw.io | [diagrams.md](./diagrams.md) |
| 旁侧 Canvas | [canvas.md](./canvas.md) |
| 模型与 Provider | [model-settings.md](./model-settings.md) |
| 插件与前端槽位 | [plugins.md](./plugins.md) |
| 工作台布局 | [client-architecture.md](./client-architecture.md) |

更完整的架构说明：[architecture.md](./architecture.md)。文档索引：[README.md](./README.md)。
