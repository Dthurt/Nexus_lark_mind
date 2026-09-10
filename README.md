# Nexus-Lark-Mind

个人自用、高解耦、分层清晰的现代化 AI Agent 编排平台。

## 架构一览

```
Adapters (飞书/Web)  →  Orchestrator (队列/会话/事件)  →  Core Kernel (模型网关/插件/SQLite)
         ↑________________ Redis Event Bus ________________↑
```

| 进程 | 端口 | 职责 |
|------|------|------|
| `adapters` | 8000 | 飞书 webhook / 长连接、Web SSE 对话页 |
| `orchestrator` | 8002 | 任务队列、会话缓存、内核 RPC 调度、事件转发 |
| `core-kernel` | 8001 | 模型网关、插件运行时、**唯一** SQLite 读写 |
| `redis` | 6379 | 任务队列 + 全局事件总线 |

依赖单向：Adapters → Orchestrator → Kernel → Infrastructure。  
**只有 Core Kernel 可以读写 SQLite**；其他服务一律经 HTTP RPC。

## 一键启动

```bash
# Windows（本机三进程 + memory broker，无需 Docker/Redis）
scripts\start_local.bat

# Docker Compose（推荐生产/联调）
cp .env.example .env
mkdir -p data logs
docker compose up --build -d

# 需要 Crawl4AI 网页抓取时（更大镜像）
docker compose -f docker-compose.yml -f docker-compose.crawl.yml up --build -d
```

启动后：

- Web 对话：http://localhost:8000
- Kernel 健康检查：http://localhost:8001/health
- Orchestrator：http://localhost:8002/health

未配置模型密钥时进入 **demo mode**（回声回复），保证 compose 可直接跑通。

镜像说明：

| 文件 | 用途 |
|------|------|
| `Dockerfile` | 默认多阶段构建（Vue → Python），不含 Playwright |
| `Dockerfile.crawl` | 含 Crawl4AI + Chromium |
| `docker-compose.yml` | redis + kernel + orchestrator + adapters |
| `docker-compose.dev.yml` | 挂载 `src/` 便于改代码热重启 |
| `docker-compose.crawl.yml` | 切换 crawl 镜像 |
## 配置

编辑 `.env`：

- `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY`
- 飞书：`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_VERIFICATION_TOKEN` / `FEISHU_ENCRYPT_KEY`

详见 [docs/architecture.md](docs/architecture.md)、[docs/diagrams.md](docs/diagrams.md)、[docs/experience-tiers.md](docs/experience-tiers.md)、[docs/interaction-modes.md](docs/interaction-modes.md)。

## 插件

- 将 CLI 脚本丢进 `plugins_volume/cli/`（`.py` / `.sh` / `.js` / `.ps1`），内核启动时自动注册
- MCP：在 `plugins_volume/mcp/*.json` 声明 `mcp_stdio` 或 `mcp_http` 清单
- RPC：`POST /rpc/plugins/load|unload|enable|disable|invoke`

## 本地开发（不经 Docker）

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 先启动本机 Redis，再分别开三个进程：
python -m src.entry_kernel
python -m src.entry_orchestrator
python -m src.entry_adapters
```

## 测试

```bash
pytest -q
```

可选网页抓取依赖：

```bash
pip install -r requirements-crawl.txt
crawl4ai-setup   # 安装 Playwright Chromium
```

GitHub Actions：`.github/workflows/ci.yml`（pytest + Vue build + compose config），`.github/workflows/docker-image.yml`（构建并推送 GHCR）。

## 目录

严格按分层放置，禁止跨层反向依赖。完整说明见 `docs/`。
