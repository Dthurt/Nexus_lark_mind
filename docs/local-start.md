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

脚本会自动：创建 venv → 安装依赖 → 用内存总线拉起三服务。

## 访问

- Web：http://127.0.0.1:8000
- Kernel：http://127.0.0.1:8001/health
- Orchestrator：http://127.0.0.1:8002/health

## 说明

本地模式使用 `REDIS_URL=memory://local`，三服务跑在同一进程（`src.entry_local`），不需要 Redis / Docker。
