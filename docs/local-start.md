# 本地部署与调试

本机跑 Nexus Lark Mind **不需要 Docker / Redis**。三服务（Adapters / Kernel / Orchestrator）在同一进程里，用内存总线（`REDIS_URL=memory://local`）。

## 两种模式怎么选

| 场景 | 命令 | 打开地址 | 说明 |
|------|------|----------|------|
| **推荐一键** | `./nlm`（Linux/macOS）· `nlm.cmd`（Windows） | http://127.0.0.1:8000 | Rich TUI：环境检查 → 依赖 → 配置 → 启动 / 修复 |
| **日常使用 / 验收** | `nlm start` / `scripts\start_local.bat` | http://127.0.0.1:8000 | 一键启动；Windows 另有无菜单 bat |
| **前端调试（HMR）** | `scripts\dev.bat` / `scripts/dev.ps1` | http://127.0.0.1:5173 | 后端 + Vite，改 React 即时刷新 |
| **只改后端** | `nlm start` | :8000 | 改 Python 后需重启进程 |
| **交付静态前端** | `scripts\build_web.bat` | — | 输出到 `web-static/`，供 :8000 / Docker |

> [!IMPORTANT]
> 前端调试请打开 **5173**，不要只看 8000。8000 上的页面是上次 `build_web` 的静态包，不会热更新。

---

## 前提

- **Python 3.10–3.13**（Linux：`python3` + `python3-venv`；Windows：勾选 Add to PATH）
  - 若本机没有可用解释器（或只有 Microsoft Store 占位的 `python.exe` / 损坏的 `py`），`nlm` / `nlm.cmd` / `nlm.ps1` **不会闪退**：会提示并给出选项——`[1]` 自动安装（Windows: winget Python 3.12；macOS: brew；Linux: apt/dnf/pacman，可能需要 sudo）、`[2]` 打开说明/下载页、`[3]` 退出。安装成功后会刷新当前进程 PATH 并继续原来的 `nlm start`。
  - `scripts\start_local.bat` / `start_local.ps1` 同样跳过 Store 占位、校验 3.10–3.13；缺解释器时交给 `nlm.ps1` 弹出上述菜单，装好后继续 start_local。双击失败会 `pause`，不会空白闪退。
  - 非交互（`nlm start --yes` / `NLM_YES=1` / CI / 无 TTY）只打印错误和安装命令后以退出码 1 结束，**不会卡住**。
- 前端调试另需 [Node.js 20+](https://nodejs.org/)（或仓库内 `.tools\node\…` 便携包）
- （可选）在 `.env` 填模型 Key；不填则为 demo 回声模式

```bash
cp .env.example .env   # 首次（或用 nlm config 向导）
```

---

## 一键启动（推荐：`nlm`，Windows + Linux）

仓库根目录：

**Linux / macOS**

```bash
chmod +x nlm          # 首次
./nlm
./nlm start
./nlm setup
./nlm config
./nlm crawl
./nlm status          # doctor
./nlm doctor
./nlm stop
./nlm restart
./nlm repair
./nlm logs
./nlm update          # git pull + setup
./scripts/start_local.sh start|stop|status
./scripts/dev.sh                 # Vite HMR
```

**Windows**

```bat
nlm
nlm start
nlm setup
nlm config
nlm crawl
nlm status
nlm doctor
nlm stop
nlm restart
nlm repair
nlm logs
nlm update
```

PowerShell：

```powershell
.\nlm.ps1
.\nlm.ps1 start
```

等价：`python -m src boot` / `python3 -m src boot start`

`nlm` 会：

1. 检查 Python / `.venv` / 端口 / `web-static` / Node / API Key
2. 按需创建 venv；**多镜像重试**安装依赖（官方 / 清华 / 阿里 / 豆瓣）
3. Rich 装不上时自动降级纯文本 UI（不再崩溃）
4. 交互配置供应商（含 Custom OpenAI-compatible）→ 写入 `.env`
5. 损坏 `.venv` / 占用端口自动修复；可选 Crawl4AI
6. Ctrl+C 优雅停服；`nlm repair` / `nlm update` 自愈与升级

---

## 轻量脚本（Windows，无菜单）

```bat
scripts\start_local.bat
```

或 PowerShell：

```powershell
.\scripts\start_local.ps1
.\scripts\start_local.ps1 -Open          # 就绪后打开浏览器
.\scripts\start_local.ps1 -Install       # 强制重装 Python 依赖
.\scripts\start_local.ps1 status         # 探活
.\scripts\start_local.ps1 stop           # 释放 8000/8001/8002
```

脚本会：

1. 解析本机 Python → 创建/复用 `.venv`
2. **仅在 `requirements.txt` 变化时** pip 安装（可用 `-Install` / `-SkipInstall` 覆盖）
3. 没有 `.env` 时从 `.env.example` 复制
4. 释放占用的 8000 / 8001 / 8002
5. 启动 `python -m src.entry_local`

### 访问

| 服务 | URL |
|------|-----|
| Web UI | http://127.0.0.1:8000 |
| Kernel | http://127.0.0.1:8001/health |
| Orchestrator | http://127.0.0.1:8002/health |

---

## 前端调试（推荐日常改 UI）

```bat
scripts\dev.bat
```

Linux / macOS：

```bash
./scripts/dev.sh
./scripts/dev.sh --no-open
./scripts/dev.sh --backend-only
```

```powershell
.\scripts\dev.ps1
.\scripts\dev.ps1 -NoOpen        # 不自动开浏览器
.\scripts\dev.ps1 -BackendOnly   # 只起后端
.\scripts\dev.ps1 -FrontendOnly  # 后端已在跑时只起 Vite
```

流程：

1. 后台拉起与 `start_local` 相同的后端
2. 等待 `:8000/health` 就绪
3. 在 `web/` 跑 `npm run dev`（Vite `:5173`，`/api` 代理到后端，SSE 不超时）
4. Ctrl+C 结束 Vite，并清理后端端口

改 `web/src/**` 后浏览器自动热更新；改 Python 仍需重启后端（再跑一次 `dev.bat` 或 `start_local`）。

### 静态包 vs HMR

| | `:8000`（web-static） | `:5173`（Vite） |
|--|----------------------|-----------------|
| 来源 | `npm run build` 产物 | 源码即时编译 |
| 何时用 | 验收、Docker、飞书联调整页 | 改 Composer / 主题 / 组件 |
| 更新方式 | `scripts\build_web.bat` 后刷新 | 保存即更新 |

---

## 停止与探活

```bat
scripts\start_local.bat stop
scripts\start_local.bat status
```

运行中的启动窗口也可 **Ctrl+C**。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 改了前端但 :8000 没变 | 你在看静态包。用 `dev.bat` 开 :5173，或先 `build_web.bat` 再刷新 :8000 |
| 加号里切模型点了没反应 | 确认已拉最新前端构建；旧包有 Select 被菜单关掉的问题 |
| 端口被占用 | `scripts\start_local.bat stop` 后再 start |
| `web-static` 缺失 | `scripts\build_web.bat`，或直接用 `dev.bat` |
| pip 太慢 / 想跳过 | 默认已跳过未变更依赖；强制：`-Install`；跳过：`-SkipInstall` |
| 没有模型 Key | 可启动，对话为 demo 回声；在 Settings → Models 或 `.env` 配置 |
| 双击 `nlm.cmd` / `start_local.bat` 一闪就关 / 提示没有 Python | 已改为停留并给出安装选项；选 `[1]` 用 winget 装 3.12，或手动装后勾选 Add to PATH |
| 飞书收不到消息 | 需本机进程在线 + 开放平台长连接事件订阅，见 [channels.md](./channels.md) |

---

## 与 Docker 的关系

| 方式 | 适用 |
|------|------|
| `scripts\start_local.*` / `dev.*` | 本机日常开发，最快 |
| `docker compose up --build -d` | 接近生产、需要真实 Redis、服务器部署 |

本地脚本会覆盖会话内环境变量（`REDIS_URL=memory://local`、本机 RPC URL），**不会改写** `.env` 里的密钥。

更完整的架构见 [architecture.md](./architecture.md)；知识库见 [knowledge-base.md](./knowledge-base.md)；飞书卡片见 [channels.md](./channels.md)；无头控制见 [headless-sdk.md](./headless-sdk.md)。
