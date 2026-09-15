#!/usr/bin/env python3
"""Nexus Lark Mind — premium local console (one command to setup + run).

Usage:
  nlm                 Interactive menu (recommended)
  nlm start           Check env → deps → config → launch
  nlm setup           Environment + deps + .env wizard
  nlm config          Configure default provider / model / keys
  nlm crawl           Install Crawl4AI + Playwright browsers
  nlm status          Health check
  nlm stop            Free ports 8000/8001/8002
  nlm repair          Auto-fix common local issues
  nlm open            Open Web UI in browser
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
    "python.exe" if os.name == "nt" else "python"
)
REQ = ROOT / "requirements.txt"
REQ_CRAWL = ROOT / "requirements-crawl.txt"
REQ_HASH = ROOT / ".venv" / ".nlm_req_hash"
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
PORTS = (8000, 8001, 8002)

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "glm": {
        "label": "智谱 GLM",
        "key_var": "GLM_API_KEY",
        "base_var": "GLM_BASE_URL",
        "model_var": "GLM_DEFAULT_MODEL",
        "default_base": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4.7-flash",
        "provider_id": "glm",
    },
    "deepseek": {
        "label": "DeepSeek",
        "key_var": "DEEPSEEK_API_KEY",
        "base_var": "DEEPSEEK_BASE_URL",
        "model_var": "DEEPSEEK_DEFAULT_MODEL",
        "default_base": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "provider_id": "deepseek",
    },
    "openai": {
        "label": "OpenAI / 兼容代理",
        "key_var": "OPENAI_API_KEY",
        "base_var": "OPENAI_BASE_URL",
        "model_var": "OPENAI_DEFAULT_MODEL",
        "default_base": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "provider_id": "openai",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "key_var": "ANTHROPIC_API_KEY",
        "base_var": "ANTHROPIC_BASE_URL",
        "model_var": "ANTHROPIC_DEFAULT_MODEL",
        "default_base": "https://api.anthropic.com",
        "default_model": "claude-3-5-sonnet-20241022",
        "provider_id": "anthropic",
    },
}


# ---------------------------------------------------------------------------
# Bootstrap rich (may not be installed yet)
# ---------------------------------------------------------------------------

def _ensure_rich() -> Any:
    try:
        from rich.console import Console
        from rich import box  # noqa: F401
        return True
    except ImportError:
        print("[nlm] Installing rich (terminal UI)…", flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "rich==13.9.4"],
        )
        return True


_ensure_rich()

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

THEME = Theme(
    {
        "info": "cyan",
        "ok": "bold green",
        "warn": "bold yellow",
        "err": "bold red",
        "muted": "dim",
        "brand": "bold cyan",
        "accent": "bold turquoise2",
    }
)
console = Console(theme=THEME)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner() -> None:
    # Prefer a compact brand panel — avoids legacy code-page mojibake of big ASCII art.
    title = Text()
    title.append("NEXUS LARK MIND", style="bold cyan")
    title.append("\n")
    title.append("Local Console", style="turquoise2")
    title.append("  ·  ", style="dim")
    title.append("setup · configure · crawl · start · repair", style="dim")
    console.print(
        Panel(
            Align.center(title),
            border_style="cyan",
            box=box.DOUBLE_EDGE,
            padding=(1, 4),
        )
    )


def step(title: str) -> None:
    console.print(Rule(f"[accent]{title}[/accent]", style="cyan"))


def ok(msg: str) -> None:
    console.print(f"[ok]✓[/ok] {msg}")


def warn(msg: str) -> None:
    console.print(f"[warn]![/warn] {msg}")


def err(msg: str) -> None:
    console.print(f"[err]✗[/err] {msg}")


def info(msg: str) -> None:
    console.print(f"[info]·[/info] {msg}")


def run_cmd(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        check=check,
        capture_output=capture,
        text=True,
    )


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def read_env(path: Path = ENV_PATH) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    """Upsert KEY=value in .env, preserving comments/order when possible."""
    if not path.exists():
        if ENV_EXAMPLE.exists():
            path.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    replaced = False
    new_lines: List[str] = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"# set by nlm wizard")
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def find_system_python() -> Optional[str]:
    """Prefer a real 3.11+ interpreter on Windows, Linux, and macOS."""
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python312/python.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python311/python.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python313/python.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c)
    else:
        for name in ("python3.13", "python3.12", "python3.11", "python3"):
            p = shutil.which(name)
            if p:
                return p

    # Prefer the interpreter currently running this script if it's 3.11+
    if sys.version_info >= (3, 11):
        return sys.executable

    for name in ("python3", "python"):
        p = shutil.which(name)
        if p and "WindowsApps" not in p:
            return p
    return None


def venv_python() -> Path:
    return VENV_PY


def ensure_dirs() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _pids_listening_on_port(port: int) -> set[int]:
    pids: set[int] = set()
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return pids
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        pids.add(int(parts[-1]))
                    except ValueError:
                        pass
        return pids

    # Linux / macOS: lsof → fuser → ss
    if shutil.which("lsof"):
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f":{port}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for tok in out.split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
            if pids:
                return pids
        except subprocess.CalledProcessError:
            pass
        except Exception:
            pass

    if shutil.which("fuser"):
        try:
            out = subprocess.check_output(
                ["fuser", f"{port}/tcp"],
                text=True,
                stderr=subprocess.STDOUT,
            )
            for tok in out.replace(":", " ").split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
            if pids:
                return pids
        except subprocess.CalledProcessError as exc:
            blob = exc.output or ""
            for tok in str(blob).replace(":", " ").split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
            if pids:
                return pids
        except Exception:
            pass

    if shutil.which("ss"):
        try:
            out = subprocess.check_output(
                ["ss", "-ltnp", f"sport = :{port}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for m in re.finditer(r"pid=(\d+)", out):
                pids.add(int(m.group(1)))
        except Exception:
            pass
    return pids


def free_ports() -> None:
    import signal

    for port in PORTS:
        pids = _pids_listening_on_port(port)
        if not pids and port_in_use(port):
            warn(f"Port {port} busy but PID unknown — free it manually.")
            continue
        for pid in sorted(pids):
            if pid <= 0:
                continue
            # Never kill our own process tree by accident on weird PID 0/1
            if pid == os.getpid() or pid == 1:
                continue
            info(f"Stopping PID {pid} on :{port}")
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    warn(f"No permission to stop PID {pid} on :{port}")
                    continue
                # Brief wait then escalate
                time.sleep(0.4)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass



def health_urls() -> List[Tuple[str, str]]:
    return [
        ("Web / Adapters", "http://127.0.0.1:8000/health"),
        ("Kernel", "http://127.0.0.1:8001/health"),
        ("Orchestrator", "http://127.0.0.1:8002/health"),
    ]


def probe_health(timeout: float = 2.0) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="accent")
    table.add_column("Service")
    table.add_column("URL")
    table.add_column("Status")
    for name, url in health_urls():
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                code = getattr(resp, "status", 200)
                if 200 <= int(code) < 300:
                    table.add_row(name, url, "[ok]OK[/ok]")
                else:
                    table.add_row(name, url, f"[err]HTTP {code}[/err]")
        except Exception:
            table.add_row(name, url, "[warn]DOWN[/warn]")
    return table


def wait_healthy(seconds: int = 45) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        ok_all = True
        for _, url in health_urls():
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if not (200 <= int(getattr(resp, "status", 200)) < 300):
                        ok_all = False
                        break
            except Exception:
                ok_all = False
                break
        if ok_all:
            return True
        time.sleep(0.8)
    return False


def local_runtime_env() -> Dict[str, str]:
    env = os.environ.copy()
    env["KERNEL_RPC_URL"] = "http://127.0.0.1:8001"
    env["ORCHESTRATOR_RPC_URL"] = "http://127.0.0.1:8002"
    env["REDIS_URL"] = "memory://local"
    env["PLUGINS_DIR"] = "plugins_volume"
    env["WEB_STATIC_DIR"] = "web-static"
    env["DATABASE_URL"] = "sqlite+aiosqlite:///data/nexus.db"
    env["PYTHONPATH"] = str(ROOT)
    return env


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------

def check_python() -> Tuple[bool, str]:
    ver = sys.version_info
    msg = f"Python {ver.major}.{ver.minor}.{ver.micro} ({sys.executable})"
    if ver < (3, 11):
        return False, msg + " — need 3.11+"
    return True, msg


def ensure_venv() -> bool:
    py = find_system_python()
    if not py:
        err("Python 3.11+ not found. Install from https://www.python.org/downloads/ (Add to PATH).")
        return False
    if venv_python().is_file():
        ok(f"venv ready · {venv_python()}")
        return True
    step("Create virtualenv")
    with Progress(SpinnerColumn(), TextColumn(), console=console) as progress:
        progress.add_task("python -m venv .venv", total=None)
        run_cmd([py, "-m", "venv", str(ROOT / ".venv")])
    ok("Created .venv")
    return True


def install_deps(*, force: bool = False, with_crawl: bool = False) -> bool:
    if not venv_python().is_file():
        err("venv missing")
        return False
    want = force
    if not want and REQ.exists():
        digest = file_sha256(REQ)
        prev = REQ_HASH.read_text(encoding="utf-8").strip() if REQ_HASH.exists() else ""
        want = digest != prev
    if with_crawl:
        want = True

    if not want:
        ok("Python deps up to date (use setup --force to reinstall)")
        return True

    step("Install Python dependencies")
    py = str(venv_python())
    with Progress(SpinnerColumn(), TextColumn(), console=console) as progress:
        t = progress.add_task("pip install -r requirements.txt", total=None)
        run_cmd([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
        run_cmd([py, "-m", "pip", "install", "-q", "-r", str(REQ)])
        progress.update(t, description="requirements.txt OK")
        if with_crawl and REQ_CRAWL.exists():
            progress.update(t, description="pip install crawl4ai…")
            run_cmd([py, "-m", "pip", "install", "-q", "-r", str(REQ_CRAWL)])
            progress.update(t, description="crawl4ai-setup (Playwright)…")
            crawl_bin = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
                "crawl4ai-setup.exe" if os.name == "nt" else "crawl4ai-setup"
            )
            if crawl_bin.exists():
                run_cmd([str(crawl_bin)], check=False)
            else:
                run_cmd(
                    [py, "-c", "import shutil,subprocess; p=shutil.which('crawl4ai-setup'); "
                     "subprocess.call([p] if p else ['echo','crawl4ai-setup not found'])"],
                    check=False,
                )
    if REQ.exists():
        REQ_HASH.parent.mkdir(parents=True, exist_ok=True)
        REQ_HASH.write_text(file_sha256(REQ), encoding="utf-8")
    ok("Dependencies installed")
    return True


def ensure_env_file() -> None:
    if ENV_PATH.exists():
        ok(f".env present · {ENV_PATH}")
        return
    if ENV_EXAMPLE.exists():
        ENV_PATH.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        ok("Created .env from .env.example")
    else:
        ENV_PATH.write_text("", encoding="utf-8")
        warn("Created empty .env")


def fix_docker_urls_in_env() -> None:
    """Replace compose hostnames with localhost for script mode."""
    if not ENV_PATH.exists():
        return
    env = read_env()
    changes = {
        "KERNEL_RPC_URL": "http://127.0.0.1:8001",
        "ORCHESTRATOR_RPC_URL": "http://127.0.0.1:8002",
        "REDIS_URL": "memory://local",
        "PLUGINS_DIR": "plugins_volume",
        "WEB_STATIC_DIR": "web-static",
        "DATABASE_URL": "sqlite+aiosqlite:///data/nexus.db",
    }
    dirty = False
    for k, v in changes.items():
        cur = env.get(k, "")
        if k == "REDIS_URL" and cur.startswith("redis://redis"):
            write_env_value(k, v)
            dirty = True
        elif "core-kernel" in cur or "orchestrator:" in cur or cur.startswith("/app/"):
            write_env_value(k, v)
            dirty = True
        elif k in ("KERNEL_RPC_URL", "ORCHESTRATOR_RPC_URL") and not cur:
            write_env_value(k, v)
            dirty = True
    if dirty:
        ok("Normalized .env for local (memory broker + 127.0.0.1 RPC)")


def config_wizard(*, non_interactive: bool = False) -> None:
    step("Model provider wizard")
    ensure_env_file()
    if non_interactive:
        info("Non-interactive: skipped prompts (edit .env later)")
        return

    console.print(
        Panel(
            "选择默认供应商并填写 API Key / Base URL / 模型名。\n"
            "可稍后在 Web Settings → Models 再改。",
            title="Configuration",
            border_style="cyan",
        )
    )
    keys = list(PROVIDER_PRESETS.keys())
    labels = [f"{i+1}. {PROVIDER_PRESETS[k]['label']}  ({k})" for i, k in enumerate(keys)]
    console.print("\n".join(labels))
    console.print("5. 跳过（稍后再配）")
    choice = Prompt.ask("选择", choices=["1", "2", "3", "4", "5"], default="1")
    if choice == "5":
        info("Skipped provider config")
        return
    pid = keys[int(choice) - 1]
    preset = PROVIDER_PRESETS[pid]
    console.print(f"\n[accent]{preset['label']}[/accent]")
    api_key = Prompt.ask(f"{preset['key_var']}", password=True, default="")
    base = Prompt.ask(f"{preset['base_var']}", default=preset["default_base"])
    model = Prompt.ask(f"{preset['model_var']}", default=preset["default_model"])

    write_env_value("DEFAULT_MODEL_PROVIDER", preset["provider_id"])
    write_env_value("DEFAULT_MODEL_NAME", model)
    write_env_value(preset["base_var"], base)
    write_env_value(preset["model_var"], model)
    if api_key.strip():
        write_env_value(preset["key_var"], api_key.strip())
    ok(f"Default provider → {preset['provider_id']} / {model}")


def install_crawl(*, ask: bool = True) -> bool:
    step("Install web crawl stack (Crawl4AI + Playwright)")
    if ask and not Confirm.ask("Crawl4AI 体积较大（含 Chromium）。继续安装？", default=True):
        info("Skipped crawl install")
        return False
    return install_deps(force=True, with_crawl=True)


def check_web_static() -> None:
    index = ROOT / "web-static" / "index.html"
    if index.is_file():
        ok("web-static ready")
        return
    warn("web-static/index.html missing — UI on :8000 will be empty until you build")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node and npm and (ROOT / "web" / "package.json").is_file():
        if Confirm.ask("检测到 Node.js，现在构建前端？", default=True):
            with Progress(SpinnerColumn(), TextColumn(), console=console) as progress:
                progress.add_task("npm install && npm run build", total=None)
                run_cmd([npm, "install"], cwd=ROOT / "web")
                run_cmd([npm, "run", "build"], cwd=ROOT / "web")
            if index.is_file():
                ok("Frontend built → web-static/")
            else:
                err("Build finished but index.html still missing")
    else:
        info("Tip: install Node 20+ then run scripts\\build_web.bat, or use scripts\\dev.bat for HMR")


def diagnose() -> Table:
    table = Table(title="Environment", box=box.ROUNDED, border_style="cyan")
    table.add_column("Check")
    table.add_column("Result")
    good, py_msg = check_python()
    table.add_row("Python", f"[ok]{py_msg}[/ok]" if good else f"[err]{py_msg}[/err]")
    table.add_row("venv", "[ok]yes[/ok]" if venv_python().is_file() else "[err]missing[/err]")
    table.add_row(".env", "[ok]yes[/ok]" if ENV_PATH.exists() else "[warn]missing[/warn]")
    table.add_row(
        "web-static",
        "[ok]yes[/ok]" if (ROOT / "web-static" / "index.html").is_file() else "[warn]missing[/warn]",
    )
    env = read_env()
    prov = env.get("DEFAULT_MODEL_PROVIDER") or "(unset)"
    model = env.get("DEFAULT_MODEL_NAME") or "(unset)"
    table.add_row("Default model", f"{prov} / {model}")
    key_ok = False
    for p in PROVIDER_PRESETS.values():
        if env.get(p["key_var"]):
            key_ok = True
            break
    table.add_row("API key", "[ok]configured[/ok]" if key_ok else "[warn]none (demo echo mode)[/warn]")
    for port in PORTS:
        table.add_row(f"Port :{port}", "[warn]busy[/warn]" if port_in_use(port) else "[ok]free[/ok]")
    try:
        import crawl4ai  # type: ignore  # noqa: F401

        table.add_row("Crawl4AI", "[ok]installed[/ok]")
    except Exception:
        table.add_row("Crawl4AI", "[muted]optional · not installed[/muted]")
    return table


def repair() -> None:
    step("Auto repair")
    ensure_dirs()
    if not ensure_venv():
        return
    install_deps(force=True)
    ensure_env_file()
    fix_docker_urls_in_env()
    free_ports()
    check_web_static()
    ok("Repair pass complete")
    console.print(diagnose())


def setup_flow(*, force: bool = False, with_crawl: bool = False, skip_config: bool = False) -> bool:
    banner()
    step("Environment check")
    console.print(diagnose())
    good, _ = check_python()
    if not good:
        err("Upgrade Python to 3.11+ first")
        return False
    if not ensure_venv():
        return False
    # Re-exec under venv if we're on system python without deps
    if Path(sys.executable).resolve() != venv_python().resolve() and venv_python().is_file():
        info("Switching into .venv …")
        os.execv(str(venv_python()), [str(venv_python()), str(Path(__file__).resolve()), *sys.argv[1:]])

    ensure_dirs()
    install_deps(force=force, with_crawl=with_crawl)
    ensure_env_file()
    fix_docker_urls_in_env()
    if not skip_config:
        env = read_env()
        need = not any(env.get(p["key_var"]) for p in PROVIDER_PRESETS.values())
        if need or Confirm.ask("运行模型配置向导？", default=need):
            config_wizard()
    if with_crawl or Confirm.ask("安装网页爬取能力 (Crawl4AI)？", default=True):
        install_crawl(ask=False)
    check_web_static()
    ok("Setup finished")
    return True


def _has_any_api_key() -> bool:
    env = read_env()
    return any(bool(env.get(p["key_var"])) for p in PROVIDER_PRESETS.values())


def start_flow(*, open_browser: bool = True, skip_setup: bool = False) -> int:
    if not skip_setup:
        if not setup_flow(skip_config=_has_any_api_key()):
            return 1
    else:
        banner()
        ensure_dirs()
        ensure_env_file()
        fix_docker_urls_in_env()

    step("Pre-flight")
    free_ports()
    console.print(diagnose())

    step("Launch")
    console.print(
        Panel(
            Group(
                Text.from_markup("[accent]Web UI[/accent]        http://127.0.0.1:8000"),
                Text.from_markup("[accent]Kernel[/accent]        http://127.0.0.1:8001/health"),
                Text.from_markup("[accent]Orchestrator[/accent]  http://127.0.0.1:8002/health"),
                Text.from_markup("[muted]Broker[/muted]         memory://local"),
                Text(""),
                Text.from_markup("[muted]Ctrl+C to stop · nlm stop · nlm status[/muted]"),
            ),
            title="Services",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    env = local_runtime_env()
    py = str(venv_python() if venv_python().is_file() else sys.executable)

    if open_browser:
        def _open() -> None:
            if wait_healthy(60):
                try:
                    webbrowser.open("http://127.0.0.1:8000")
                except Exception:
                    pass

        import threading

        threading.Thread(target=_open, daemon=True).start()

    try:
        proc = subprocess.Popen(
            [py, "-m", "src.entry_local"],
            cwd=str(ROOT),
            env=env,
        )
        return proc.wait()
    except KeyboardInterrupt:
        console.print("\n[warn]Stopping…[/warn]")
        free_ports()
        return 0


def menu() -> int:
    banner()
    console.print(diagnose())
    console.print()
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Key", style="accent", width=4)
    table.add_column("Action")
    table.add_row("1", "一键启动  — 环境检查 → 依赖 → 配置 → 启动（推荐）")
    table.add_row("2", "安装 / 修复环境")
    table.add_row("3", "配置向导  — 默认供应商 / 模型 / API Key / Base URL")
    table.add_row("4", "安装网页爬取 (Crawl4AI + Playwright)")
    table.add_row("5", "状态检查")
    table.add_row("6", "停止服务（释放 8000–8002）")
    table.add_row("7", "打开 Web UI")
    table.add_row("0", "退出")
    console.print(Panel(table, title="Menu", border_style="cyan", box=box.ROUNDED))

    choice = Prompt.ask("选择", choices=list("01234567"), default="1")
    if choice == "0":
        return 0
    if choice == "1":
        return start_flow(open_browser=Confirm.ask("启动后打开浏览器？", default=True))
    if choice == "2":
        repair()
        return 0
    if choice == "3":
        ensure_env_file()
        config_wizard()
        return 0
    if choice == "4":
        ensure_venv()
        install_crawl()
        return 0
    if choice == "5":
        console.print(probe_health())
        return 0
    if choice == "6":
        free_ports()
        ok("Ports cleared")
        return 0
    if choice == "7":
        webbrowser.open("http://127.0.0.1:8000")
        ok("Opened http://127.0.0.1:8000")
        return 0
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(
        prog="nlm",
        description="Nexus Lark Mind local console — setup, configure, run, repair",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="One-shot setup + launch")
    p_start.add_argument("--no-open", action="store_true")
    p_start.add_argument("--skip-setup", action="store_true")

    p_setup = sub.add_parser("setup", help="Install env/deps and configure")
    p_setup.add_argument("--force", action="store_true")
    p_setup.add_argument("--crawl", action="store_true")
    p_setup.add_argument("--skip-config", action="store_true")

    sub.add_parser("config", help="Provider / model / API wizard")
    sub.add_parser("crawl", help="Install Crawl4AI + Playwright")
    sub.add_parser("status", help="Health check")
    sub.add_parser("stop", help="Free local ports")
    sub.add_parser("repair", help="Auto-fix common issues")
    sub.add_parser("open", help="Open Web UI")
    sub.add_parser("menu", help="Interactive menu (default)")

    args = parser.parse_args(argv)
    cmd = args.cmd or "menu"

    if cmd == "menu":
        return menu()
    if cmd == "start":
        return start_flow(open_browser=not args.no_open, skip_setup=args.skip_setup)
    if cmd == "setup":
        return 0 if setup_flow(force=args.force, with_crawl=args.crawl, skip_config=args.skip_config) else 1
    if cmd == "config":
        ensure_env_file()
        config_wizard()
        return 0
    if cmd == "crawl":
        ensure_venv()
        return 0 if install_crawl() else 1
    if cmd == "status":
        banner()
        console.print(diagnose())
        console.print(probe_health())
        return 0
    if cmd == "stop":
        free_ports()
        ok("Stopped")
        return 0
    if cmd == "repair":
        repair()
        return 0
    if cmd == "open":
        webbrowser.open("http://127.0.0.1:8000")
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
