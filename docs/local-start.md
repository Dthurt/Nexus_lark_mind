# 本地脚本启动（无需 Docker / Redis）

## 前提

安装 [Python 3.11+](https://www.python.org/downloads/windows/)，勾选 **Add python.exe to PATH**。

## 一键启动

```bat
cd E:\cursor\open_program\Nexus_lark_mind
scripts\start_local.bat
```

或 PowerShell：

```powershell
cd E:\cursor\open_program\Nexus_lark_mind
.\scripts\start_local.ps1
```

或（Wave E/F）`nlm` / 模块入口：

```bat
scripts\nlm.cmd web --open
python -m src chat --cwd E:\proj "hello"
```

详见 [headless-sdk.md](./headless-sdk.md)。

脚本会自动：创建 venv → 安装依赖 → 用内存总线拉起三服务。启动前会释放已被占用的 8000/8001/8002。

## 停止

另开一个终端：

```bat
scripts\start_local.bat stop
```

```powershell
.\scripts\start_local.ps1 stop
```

会结束占用 8000/8001/8002 的进程。运行中的窗口也可用 Ctrl+C。

## 访问

- Web：http://127.0.0.1:8000
- Kernel：http://127.0.0.1:8001/health
- Orchestrator：http://127.0.0.1:8002/health

## 说明

本地模式使用 `REDIS_URL=memory://local`，三服务跑在同一进程（`src.entry_local`），不需要 Redis / Docker。
