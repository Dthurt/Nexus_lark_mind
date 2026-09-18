#!/usr/bin/env python3
"""Nexus Lark Mind — cross-platform local console (self-install / self-repair).

Usage:
  nlm                 Interactive menu (recommended)
  nlm start           Check env → deps → config → launch
  nlm setup           Environment + deps + .env wizard
  nlm config          Configure default provider / model / keys
  nlm crawl           Install Crawl4AI + Playwright browsers
  nlm status          Health check
  nlm stop            Free ports 8000/8001/8002
  nlm restart         Stop then start
  nlm repair          Auto-fix common local issues
  nlm doctor          Full diagnostics
  nlm logs            Tail logs/
  nlm update          git pull + re-run setup
  nlm open            Open Web UI in browser
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

def _force_utf8_stdio() -> None:
    """Avoid GBK UnicodeEncodeError on Windows (✓ / rich panels / redirected logs)."""
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


_force_utf8_stdio()

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
LOG_DIR = ROOT / "logs"
TEXT_COL = "[progress.description]{task.description}"

# Prefer official PyPI, then common CN mirrors (helps when one index times out).
PIP_INDEXES: Tuple[str, ...] = (
    "https://pypi.org/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.douban.com/simple",
)

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
# Plain UI fallback (when rich cannot be installed — e.g. offline / bad mirror)
# ---------------------------------------------------------------------------

class _PlainConsole:
    def print(self, *args: Any, **kwargs: Any) -> None:
        parts = []
        for a in args:
            parts.append(str(a))
        text = " ".join(parts)
        text = re.sub(r"\[/?[^\]]+\]", "", text)
        print(text, flush=True)


class _PlainPrompt:
    @staticmethod
    def ask(prompt: str, *, choices: Optional[List[str]] = None, default: Any = None, password: bool = False) -> str:
        hint = f" [{default}]" if default is not None else ""
        while True:
            try:
                if password:
                    import getpass

                    raw = getpass.getpass(f"{prompt}{hint}: ")
                else:
                    raw = input(f"{prompt}{hint}: ")
            except EOFError:
                raw = ""
            val = (raw or "").strip() or ("" if default is None else str(default))
            if choices is None or val in choices:
                return val
            print(f"Choose one of: {', '.join(choices)}", flush=True)


class _PlainConfirm:
    @staticmethod
    def ask(prompt: str, *, default: bool = True) -> bool:
        yn = "Y/n" if default else "y/N"
        try:
            raw = input(f"{prompt} [{yn}]: ").strip().lower()
        except EOFError:
            raw = ""
        if not raw:
            return default
        return raw in ("y", "yes", "1", "true")


class _PlainPanel:
    def __init__(self, renderable: Any, **kwargs: Any) -> None:
        self.renderable = renderable

    def __str__(self) -> str:
        return str(self.renderable)


class _PlainTable:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.rows: List[Tuple[str, ...]] = []
        self.title = kwargs.get("title", "")

    def add_column(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add_row(self, *cells: Any) -> None:
        self.rows.append(tuple(str(c) for c in cells))

    def __str__(self) -> str:
        lines = [self.title] if self.title else []
        for row in self.rows:
            lines.append("  |  ".join(re.sub(r"\[/?[^\]]+\]", "", c) for c in row))
        return "\n".join(lines)


class _PlainProgress:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._desc = ""

    def __enter__(self) -> "_PlainProgress":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def add_task(self, description: str = "", total: Any = None) -> int:
        self._desc = description
        print(f"  … {description}", flush=True)
        return 0

    def update(self, task_id: int, description: Optional[str] = None, **kwargs: Any) -> None:
        if description:
            self._desc = description
            print(f"  … {description}", flush=True)


HAS_RICH = False
console: Any = _PlainConsole()
Prompt: Any = _PlainPrompt
Confirm: Any = _PlainConfirm
Panel: Any = _PlainPanel
Table: Any = _PlainTable
Progress: Any = _PlainProgress
SpinnerColumn: Any = object
TextColumn: Any = object
Align: Any = None
Group: Any = None
Rule: Any = None
Text: Any = None
box: Any = None


def _pip_install(packages: Sequence[str], *, python: Optional[str] = None, quiet: bool = True) -> bool:
    """Install packages trying multiple indexes until one succeeds."""
    py = python or sys.executable
    q = ["-q"] if quiet else []
    last_err = ""
    for index in PIP_INDEXES:
        cmd = [
            py,
            "-m",
            "pip",
            "install",
            *q,
            "--retries",
            "2",
            "--timeout",
            "30",
            "-i",
            index,
            *packages,
        ]
        print(f"[nlm] pip install ({index}) …", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if proc.returncode == 0:
            return True
        last_err = (proc.stderr or proc.stdout or "").strip()[-400:]
        print(f"[nlm] index failed, trying next…", flush=True)
    if last_err:
        print(f"[nlm] pip error: {last_err}", flush=True)
    return False


def _pip_install_requirements(req_file: Path, *, python: Optional[str] = None) -> bool:
    py = python or sys.executable
    last_err = ""
    for index in PIP_INDEXES:
        cmd = [
            py,
            "-m",
            "pip",
            "install",
            "-q",
            "--retries",
            "2",
            "--timeout",
            "60",
            "-i",
            index,
            "-r",
            str(req_file),
        ]
        print(f"[nlm] pip install -r {req_file.name} ({index}) …", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if proc.returncode == 0:
            return True
        last_err = (proc.stderr or proc.stdout or "").strip()[-500:]
        print(f"[nlm] index failed, trying next…", flush=True)
    if last_err:
        print(f"[nlm] pip error: {last_err}", flush=True)
    return False


def _ensure_rich() -> bool:
    global HAS_RICH, console, Prompt, Confirm, Panel, Table, Progress
    global SpinnerColumn, TextColumn, Align, Group, Rule, Text, box

    def _activate() -> bool:
        global HAS_RICH, console, Prompt, Confirm, Panel, Table, Progress
        global SpinnerColumn, TextColumn, Align, Group, Rule, Text, box
        from rich import box as _box
        from rich.align import Align as _Align
        from rich.cells import cell_len
        from rich.console import Console, Group as _Group
        from rich.panel import Panel as _Panel
        from rich.progress import Progress as _Progress, SpinnerColumn as _SC, TextColumn as _TC
        from rich.prompt import Confirm as _Confirm, Prompt as _Prompt
        from rich.rule import Rule as _Rule
        from rich.table import Table as _Table
        from rich.text import Text as _Text
        from rich.theme import Theme

        # Python 3.13+ / Unicode 17 needs rich>=14.3 (_unicode_data.unicode17-0-0).
        # Probe early so we fall back to plain UI instead of crashing on Confirm.ask.
        cell_len("测试OK")

        theme = Theme(
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
        # legacy_windows=False avoids Win32 console path that blows up on GBK + ✓
        console = Console(theme=theme, legacy_windows=False, soft_wrap=True)
        Prompt, Confirm = _Prompt, _Confirm
        Panel, Table, Progress = _Panel, _Table, _Progress
        SpinnerColumn, TextColumn = _SC, _TC
        Align, Group, Rule, Text, box = _Align, _Group, _Rule, _Text, _box
        HAS_RICH = True
        return True

    try:
        return _activate()
    except Exception as first_exc:
        print(f"[nlm] Installing/upgrading rich (terminal UI)… ({first_exc.__class__.__name__})", flush=True)
        # Prefer a Unicode-17-capable build for Python 3.13+
        if not _pip_install(["rich>=14.3.0,<15"]):
            print("[nlm] WARN: rich unavailable — using plain text UI", flush=True)
            return False
        try:
            # Fresh import after upgrade
            for mod in list(sys.modules):
                if mod == "rich" or mod.startswith("rich."):
                    del sys.modules[mod]
            return _activate()
        except Exception as exc:
            print(f"[nlm] WARN: rich unusable ({exc}) — plain text UI", flush=True)
            HAS_RICH = False
            return False


_ensure_rich()


def progress_ctx() -> Any:
    if HAS_RICH:
        return Progress(SpinnerColumn(), TextColumn(TEXT_COL), console=console)
    return Progress()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner() -> None:
    if HAS_RICH and Align is not None and Text is not None:
        title = Text()
        title.append("NEXUS LARK MIND", style="bold cyan")
        title.append("\n")
        title.append("Local Console", style="turquoise2")
        title.append("  ·  ", style="dim")
        title.append("setup · configure · crawl · start · repair", style="dim")
        console.print(Panel(Align.center(title), border_style="cyan", box=box.DOUBLE_EDGE, padding=(1, 4)))
    else:
        print("=" * 60, flush=True)
        print("  NEXUS LARK MIND · Local Console", flush=True)
        print("  setup · configure · crawl · start · repair", flush=True)
        print("=" * 60, flush=True)


def step(title: str) -> None:
    if HAS_RICH and Rule is not None:
        console.print(Rule(f"[accent]{title}[/accent]", style="cyan"))
    else:
        print(f"\n=== {title} ===", flush=True)


def ok(msg: str) -> None:
    # ASCII markers — never emit ✓/✗ (GBK consoles / redirected pipes crash)
    console.print(f"[ok]+[/ok] {msg}" if HAS_RICH else f"+ {msg}")


def warn(msg: str) -> None:
    console.print(f"[warn]![/warn] {msg}" if HAS_RICH else f"! {msg}")


def err(msg: str) -> None:
    console.print(f"[err]x[/err] {msg}" if HAS_RICH else f"x {msg}")


def info(msg: str) -> None:
    console.print(f"[info]*[/info] {msg}" if HAS_RICH else f"* {msg}")


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
        new_lines.append("# set by nlm wizard")
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def is_windows_store_stub(path: Optional[str]) -> bool:
    """Microsoft Store alias (WindowsApps\\python.exe) is not a real interpreter."""
    if not path:
        return False
    return "windowsapps" in str(path).replace("/", "\\").lower()


def is_supported_python_version(ver: Optional[Tuple[int, ...]]) -> bool:
    if not ver or len(ver) < 2:
        return False
    return (3, 11) <= (int(ver[0]), int(ver[1])) <= (3, 13)


def probe_python_version(exe: str) -> Optional[Tuple[int, int, int]]:
    """Return (major, minor, micro) or None if stub / broken / unusable."""
    if not exe or is_windows_store_stub(exe):
        return None
    lowered = exe.replace("/", "\\").lower()
    if exe in ("py", "py.exe") or lowered.endswith("\\py.exe"):
        cmd = ([exe] if exe not in ("py", "py.exe") else ["py"]) + ["-3"]
    else:
        cmd = [exe]
    try:
        out = subprocess.check_output(
            [*cmd, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=12,
        ).strip()
        parts = out.split(".")
        if len(parts) < 3:
            return None
        return int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        return None


def default_windows_python_exes() -> List[Path]:
    out: List[Path] = []
    if os.name != "nt":
        return out
    roots = (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    )
    for root in roots:
        for ver in ("Python312", "Python311", "Python313"):
            out.append(root / ver / "python.exe")
    return out


def refresh_process_path() -> None:
    """Pick up a just-installed Python without requiring a new login."""
    if os.name != "nt":
        return
    parts: List[str] = []
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    for ver in ("Python312", "Python311", "Python313"):
        parts.append(str(local / ver))
        parts.append(str(local / ver / "Scripts"))
    parts.append(str(local / "Launcher"))
    for pf_key in ("ProgramFiles", "ProgramFiles(x86)"):
        pf = Path(os.environ.get(pf_key, ""))
        if str(pf):
            for ver in ("Python312", "Python311", "Python313"):
                parts.append(str(pf / ver))
    try:
        import winreg

        for hive, sub in (
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    raw, _ = winreg.QueryValueEx(key, "Path")
                    if raw:
                        parts.append(str(raw))
            except OSError:
                pass
    except Exception:
        pass
    parts.append(os.environ.get("PATH", ""))
    os.environ["PATH"] = os.pathsep.join(p for p in parts if p)


def find_system_python() -> Optional[str]:
    candidates: List[str] = []
    if os.name == "nt":
        candidates.extend(str(p) for p in default_windows_python_exes())
        for name in ("python3.13", "python3.12", "python3.11", "python3", "python"):
            p = shutil.which(name)
            if p:
                candidates.append(p)
    else:
        for name in ("python3.13", "python3.12", "python3.11", "python3"):
            p = shutil.which(name)
            if p:
                candidates.append(p)

    if is_supported_python_version(tuple(sys.version_info[:3])) and not is_windows_store_stub(sys.executable):
        candidates.append(sys.executable)

    if os.name != "nt":
        p = shutil.which("python")
        if p:
            candidates.append(p)

    seen: set[str] = set()
    for c in candidates:
        if not c:
            continue
        key = os.path.normcase(os.path.abspath(c)) if os.path.isabs(c) else os.path.normcase(c)
        if key in seen:
            continue
        seen.add(key)
        if is_windows_store_stub(c):
            continue
        if c not in ("py", "py.exe") and not Path(c).is_file():
            continue
        if is_supported_python_version(probe_python_version(c)):
            return c

    if os.name == "nt":
        py = shutil.which("py")
        if py and not is_windows_store_stub(py) and is_supported_python_version(probe_python_version("py")):
            return "py"
    return None


def is_noninteractive_cli() -> bool:
    if auto_yes():
        return True
    if os.environ.get("CI", "").strip():
        return True
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return True
    except Exception:
        return True
    return False


def missing_python_help_text(*, non_interactive: bool = False) -> str:
    lines = [
        "[nlm] 未找到可用的 Python 3.11-3.13。",
        "      Need Python 3.11-3.13 (Microsoft Store stub is not a real interpreter).",
    ]
    if os.name == "nt":
        lines += [
            "",
            "  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements",
        ]
    elif sys.platform == "darwin":
        lines += ["", "  brew install python@3.12"]
    else:
        lines += ["", "  sudo apt-get install -y python3 python3-venv python3-pip"]
        lines += ["  sudo dnf install -y python3.12 python3-pip"]
        lines += ["  sudo pacman -S --noconfirm python python-pip"]
    if non_interactive:
        lines += ["", "非交互 / non-interactive: 安装后重新运行 nlm start"]
    return "\n".join(lines)


def open_python_install_docs() -> None:
    url = "https://www.python.org/downloads/"
    if os.name == "nt":
        info("打开官网下载页。安装时请勾选 Add python.exe to PATH")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return
    if sys.platform == "darwin":
        info("macOS: brew install python@3.12")
        info(f"或下载: {url}macos/")
        opener = shutil.which("open")
        if opener:
            subprocess.run([opener, f"{url}macos/"], check=False)
        return
    info("Debian/Ubuntu: sudo apt-get install -y python3 python3-venv python3-pip")
    info("Fedora: sudo dnf install -y python3.12 python3-pip")
    info("Arch: sudo pacman -S --noconfirm python python-pip")
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        xdg = shutil.which("xdg-open")
        if xdg:
            subprocess.run([xdg, url], check=False)


def _run_privileged(cmd: List[str]) -> int:
    if os.name != "nt":
        try:
            if hasattr(os, "geteuid") and os.geteuid() == 0:  # type: ignore[attr-defined]
                return int(subprocess.run(cmd).returncode)
        except Exception:
            pass
        sudo = shutil.which("sudo")
        if sudo:
            return int(subprocess.run([sudo, *cmd]).returncode)
        err("需要 sudo 才能自动安装 Python")
        return 1
    return int(subprocess.run(cmd).returncode)


def try_install_system_python() -> Optional[str]:
    """User-consented best-effort install. Reports what was tried. May refresh PATH."""
    tried: List[str] = []
    refresh_process_path()

    if os.name == "nt":
        winget = shutil.which("winget")
        if winget:
            for pkg in ("Python.Python.3.12", "Python.Python.3.11"):
                tried.append(f"winget {pkg}")
                info(f"正在通过 winget 安装 {pkg}（用户范围）...")
                subprocess.run(
                    [
                        winget,
                        "install",
                        "-e",
                        "--id",
                        pkg,
                        "--scope",
                        "user",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                    ],
                    check=False,
                )
                refresh_process_path()
                found = find_system_python()
                if found:
                    ok(f"Python ready · {found}")
                    return found
        else:
            tried.append("winget (not installed)")
            warn("未找到 winget，打开官网下载页。请勾选 Add python.exe to PATH")
            open_python_install_docs()
        warn("已尝试: " + "; ".join(tried))
        return None

    if sys.platform == "darwin":
        brew = shutil.which("brew")
        if brew:
            tried.append("brew python@3.12")
            info("brew install python@3.12")
            subprocess.run([brew, "install", "python@3.12"], check=False)
            found = find_system_python()
            if found:
                ok(f"Python ready · {found}")
                return found
        else:
            tried.append("brew (not installed)")
            err("未找到 Homebrew，不会假装使用 apt。请: brew install python@3.12")
            info("或打开 https://www.python.org/downloads/macos/")
        warn("已尝试: " + "; ".join(tried))
        return None

    if shutil.which("apt-get"):
        info("使用 apt 安装 Python（可能需要输入 sudo 密码）...")
        _run_privileged(["apt-get", "update"])
        for pkgs in (
            ["python3.12", "python3.12-venv", "python3-pip"],
            ["python3.11", "python3.11-venv", "python3-pip"],
            ["python3", "python3-venv", "python3-pip"],
        ):
            tried.append("apt " + " ".join(pkgs))
            info("尝试: sudo apt-get install -y " + " ".join(pkgs))
            if _run_privileged(["apt-get", "install", "-y", *pkgs]) == 0:
                found = find_system_python()
                if found:
                    ok(f"Python ready · {found}")
                    return found
    elif shutil.which("dnf"):
        info("使用 dnf 安装 Python（可能需要输入 sudo 密码）...")
        for pkgs in (
            ["python3.12", "python3-pip"],
            ["python3.11", "python3-pip"],
            ["python3", "python3-pip"],
        ):
            tried.append("dnf " + " ".join(pkgs))
            if _run_privileged(["dnf", "install", "-y", *pkgs]) == 0:
                found = find_system_python()
                if found:
                    ok(f"Python ready · {found}")
                    return found
    elif shutil.which("pacman"):
        tried.append("pacman python")
        info("使用 pacman 安装 Python（可能需要输入 sudo 密码）...")
        if _run_privileged(["pacman", "-S", "--noconfirm", "python", "python-pip"]) == 0:
            found = find_system_python()
            if found:
                ok(f"Python ready · {found}")
                return found
    elif shutil.which("zypper"):
        tried.append("zypper python3")
        if _run_privileged(["zypper", "install", "-y", "python3", "python3-pip", "python3-venv"]) == 0:
            found = find_system_python()
            if found:
                ok(f"Python ready · {found}")
                return found
    elif shutil.which("apk"):
        tried.append("apk python3")
        if _run_privileged(["apk", "add", "python3", "py3-pip"]) == 0:
            found = find_system_python()
            if found:
                ok(f"Python ready · {found}")
                return found
    else:
        tried.append("no package manager")
        err("无法识别包管理器（apt/dnf/pacman/zypper/apk/brew）")

    warn("已尝试: " + "; ".join(tried) if tried else "已尝试: none")
    return None


def resolve_or_install_python() -> Optional[str]:
    """Find a real 3.11–3.13 interpreter, or prompt to install (never hang in CI / --yes)."""
    found = find_system_python()
    if found:
        return found
    print(missing_python_help_text(non_interactive=is_noninteractive_cli()), flush=True)
    if is_noninteractive_cli():
        return None
    while True:
        print("[1] 自动安装 Python 3.12（推荐）", flush=True)
        print("[2] 打开说明 / 下载页，我自己装", flush=True)
        print("[3] 退出", flush=True)
        try:
            choice = input("请选择 [1/2/3]: ").strip()
        except EOFError:
            return None
        if choice == "1":
            found = try_install_system_python()
            if found:
                return found
            warn("安装后仍未找到，可重试或选 2")
        elif choice == "2":
            open_python_install_docs()
            info("装好后重新运行 nlm，或按 1 再试")
        elif choice in ("3", ""):
            return None
        else:
            info("请输入 1、2 或 3")



def venv_python() -> Path:
    return VENV_PY


def ensure_dirs() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _pids_listening_on_port(port: int) -> set[int]:
    pids: set[int] = set()
    if os.name == "nt":
        try:
            out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
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

    if shutil.which("lsof"):
        try:
            out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True, stderr=subprocess.DEVNULL)
            for tok in out.split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
            if pids:
                return pids
        except (subprocess.CalledProcessError, Exception):
            pass

    if shutil.which("fuser"):
        try:
            out = subprocess.check_output(["fuser", f"{port}/tcp"], text=True, stderr=subprocess.STDOUT)
            for tok in out.replace(":", " ").split():
                try:
                    pids.add(int(tok))
                except ValueError:
                    pass
            if pids:
                return pids
        except subprocess.CalledProcessError as exc:
            for tok in str(exc.output or "").replace(":", " ").split():
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
                ["ss", "-ltnp", f"sport = :{port}"], text=True, stderr=subprocess.DEVNULL
            )
            for m in re.finditer(r"pid=(\d+)", out):
                pids.add(int(m.group(1)))
        except Exception:
            pass
    return pids


def free_ports() -> None:
    for port in PORTS:
        pids = _pids_listening_on_port(port)
        if not pids and port_in_use(port):
            warn(f"Port {port} busy but PID unknown — free it manually.")
            continue
        for pid in sorted(pids):
            if pid <= 0 or pid == os.getpid() or pid == 1:
                continue
            info(f"Stopping PID {pid} on :{port}")
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    warn(f"No permission to stop PID {pid} on :{port}")
                    continue
                time.sleep(0.4)
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass


def health_urls() -> List[Tuple[str, str]]:
    return [
        ("Web / Adapters", "http://127.0.0.1:8000/health"),
        ("Kernel", "http://127.0.0.1:8001/health"),
        ("Orchestrator", "http://127.0.0.1:8002/health"),
    ]


def probe_health(timeout: float = 2.0) -> Any:
    table = Table(box=box.SIMPLE_HEAVY if HAS_RICH else None, show_header=True, header_style="accent")
    table.add_column("Service")
    table.add_column("URL")
    table.add_column("Status")
    for name, url in health_urls():
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                code = int(getattr(resp, "status", 200))
                if 200 <= code < 300:
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
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def node_major_version() -> Optional[int]:
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.check_output([node, "--version"], text=True, stderr=subprocess.DEVNULL).strip()
        m = re.match(r"v?(\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------

def check_python() -> Tuple[bool, str]:
    ver = sys.version_info
    msg = f"Python {ver.major}.{ver.minor}.{ver.micro} ({sys.executable})"
    if ver < (3, 11):
        return False, msg + " — need 3.11+"
    if ver >= (3, 14):
        return False, msg + " — unsupported (use 3.11–3.13)"
    if ver >= (3, 13):
        msg += " — OK (prefer 3.11/3.12 if issues)"
    return True, msg


def ensure_venv() -> bool:
    py = resolve_or_install_python()
    if not py:
        err("无法继续：需要 Python 3.11-3.13。Need Python 3.11-3.13.")
        return False
    if venv_python().is_file():
        # Sanity: broken venv?
        try:
            subprocess.check_output([str(venv_python()), "-c", "import sys"], stderr=subprocess.DEVNULL)
            ok(f"venv ready · {venv_python()}")
            return True
        except Exception:
            warn("Broken .venv detected — recreating")
            shutil.rmtree(ROOT / ".venv", ignore_errors=True)
    step("Create virtualenv")
    with progress_ctx() as progress:
        progress.add_task("python -m venv .venv", total=None)
        try:
            run_cmd([py, "-m", "venv", str(ROOT / ".venv")])
        except subprocess.CalledProcessError:
            err("venv creation failed. On Debian/Ubuntu: sudo apt install python3-venv")
            return False
    if not venv_python().is_file():
        err("venv created but python binary missing")
        return False
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
        ok("Python deps up to date (use setup --force / repair to reinstall)")
        return True

    step("Install Python dependencies")
    py = str(venv_python())
    with progress_ctx() as progress:
        t = progress.add_task("upgrade pip", total=None)
        _pip_install(["--upgrade", "pip"], python=py)
        progress.update(t, description="pip install -r requirements.txt")
        if not _pip_install_requirements(REQ, python=py):
            err("Failed to install requirements.txt from all mirrors")
            return False
        progress.update(t, description="requirements.txt OK")
        if with_crawl and REQ_CRAWL.exists():
            progress.update(t, description="pip install crawl4ai…")
            if not _pip_install_requirements(REQ_CRAWL, python=py):
                warn("Crawl4AI install failed — core stack still usable")
            else:
                progress.update(t, description="crawl4ai-setup (Playwright)…")
                crawl_bin = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
                    "crawl4ai-setup.exe" if os.name == "nt" else "crawl4ai-setup"
                )
                if crawl_bin.exists():
                    run_cmd([str(crawl_bin)], check=False)
                else:
                    run_cmd(
                        [
                            py,
                            "-c",
                            "import shutil,subprocess; p=shutil.which('crawl4ai-setup'); "
                            "raise SystemExit(subprocess.call([p]) if p else 0)",
                        ],
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
    """Normalize known Docker-compose service hostnames for local script mode."""
    if not ENV_PATH.exists():
        return
    env = read_env()
    local_defaults = {
        "KERNEL_RPC_URL": "http://127.0.0.1:8001",
        "ORCHESTRATOR_RPC_URL": "http://127.0.0.1:8002",
        "REDIS_URL": "memory://local",
        "PLUGINS_DIR": "plugins_volume",
        "WEB_STATIC_DIR": "web-static",
        "DATABASE_URL": "sqlite+aiosqlite:///data/nexus.db",
    }
    # Only rewrite keys we own for service discovery — never touch model base URLs.
    dockerish = {
        "KERNEL_RPC_URL": ("core-kernel", "http://kernel", "kernel:"),
        "ORCHESTRATOR_RPC_URL": ("orchestrator:", "http://orchestrator"),
        "REDIS_URL": ("redis://redis",),
        "PLUGINS_DIR": ("/app/plugins",),
        "WEB_STATIC_DIR": ("/app/web-static",),
        "DATABASE_URL": ("/app/data",),
    }
    dirty = False
    for k, v in local_defaults.items():
        cur = env.get(k, "")
        if not cur and k in ("KERNEL_RPC_URL", "ORCHESTRATOR_RPC_URL", "REDIS_URL"):
            write_env_value(k, v)
            dirty = True
            continue
        markers = dockerish.get(k, ())
        if any(m in cur for m in markers):
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

    body = (
        "选择默认供应商并填写 API Key / Base URL / 模型名。\n"
        "可稍后在 Web Settings → Models 再改。"
        if HAS_RICH
        else "Configure default provider / API key / base URL / model."
    )
    console.print(Panel(body, title="Configuration", border_style="cyan") if HAS_RICH else body)

    keys = list(PROVIDER_PRESETS.keys())
    for i, k in enumerate(keys, 1):
        console.print(f"{i}. {PROVIDER_PRESETS[k]['label']}  ({k})")
    console.print("5. Custom OpenAI-compatible (vLLM / Ollama / LM Studio / Azure…)")
    console.print("6. 跳过（稍后再配）")
    choice = ask_text("选择", choices=["1", "2", "3", "4", "5", "6"], default="1")
    if choice == "6":
        info("Skipped provider config")
        return

    if choice == "5":
        console.print("\nCustom OpenAI-compatible endpoint")
        api_key = ask_text("OPENAI_API_KEY (可空)", password=True, default="")
        base = ask_text("OPENAI_BASE_URL", default="http://127.0.0.1:11434/v1")
        model = ask_text("DEFAULT_MODEL_NAME", default="llama3.2")
        write_env_value("DEFAULT_MODEL_PROVIDER", "openai")
        write_env_value("DEFAULT_MODEL_NAME", model)
        write_env_value("OPENAI_BASE_URL", base)
        write_env_value("OPENAI_DEFAULT_MODEL", model)
        if api_key.strip():
            write_env_value("OPENAI_API_KEY", api_key.strip())
        ok(f"Default provider → openai (custom) / {model}")
        return

    pid = keys[int(choice) - 1]
    preset = PROVIDER_PRESETS[pid]
    console.print(f"\n{preset['label']}")
    api_key = ask_text(preset["key_var"], password=True, default="")
    base = ask_text(preset["base_var"], default=preset["default_base"])
    model = ask_text(preset["model_var"], default=preset["default_model"])

    write_env_value("DEFAULT_MODEL_PROVIDER", preset["provider_id"])
    write_env_value("DEFAULT_MODEL_NAME", model)
    write_env_value(preset["base_var"], base)
    write_env_value(preset["model_var"], model)
    if api_key.strip():
        write_env_value(preset["key_var"], api_key.strip())
    ok(f"Default provider → {preset['provider_id']} / {model}")


def install_crawl(*, ask: bool = True) -> bool:
    step("Install web crawl stack (Crawl4AI + Playwright)")
    if ask and not confirm("Crawl4AI 体积较大（含 Chromium）。继续安装？", default=False):
        info("Skipped crawl install")
        return False
    return install_deps(force=True, with_crawl=True)


def check_web_static(*, offer_build: bool = True) -> None:
    index = ROOT / "web-static" / "index.html"
    if index.is_file():
        ok("web-static ready")
        return
    warn("web-static/index.html missing — UI on :8000 will be empty until you build")
    major = node_major_version()
    npm = shutil.which("npm")
    if major is None or not npm:
        info("Tip: install Node.js 20+ LTS, then: cd web && npm install && npm run build")
        info("Or use scripts/dev.sh (Linux) / scripts/dev.bat (Windows) for Vite HMR")
        return
    if major < 18:
        warn(f"Node v{major} is too old — need 18+ (prefer 20 LTS)")
        return
    if not (ROOT / "web" / "package.json").is_file():
        return
    if not offer_build:
        return
    if confirm(f"检测到 Node v{major}，现在构建前端？", default=False):
        with progress_ctx() as progress:
            progress.add_task("npm install && npm run build", total=None)
            try:
                run_cmd([npm, "install"], cwd=ROOT / "web")
                run_cmd([npm, "run", "build"], cwd=ROOT / "web")
            except subprocess.CalledProcessError as exc:
                err(f"Frontend build failed: {exc}")
                return
        if index.is_file():
            ok("Frontend built → web-static/")
        else:
            err("Build finished but index.html still missing")


def diagnose() -> Any:
    table = Table(title="Environment", box=box.ROUNDED if HAS_RICH else None, border_style="cyan")
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
    major = node_major_version()
    if major is None:
        table.add_row("Node.js", "[muted]optional · not installed[/muted]")
    elif major < 18:
        table.add_row("Node.js", f"[warn]v{major} (need 18+)[/warn]")
    else:
        table.add_row("Node.js", f"[ok]v{major}[/ok]")
    env = read_env()
    prov = env.get("DEFAULT_MODEL_PROVIDER") or "(unset)"
    model = env.get("DEFAULT_MODEL_NAME") or "(unset)"
    table.add_row("Default model", f"{prov} / {model}")
    key_ok = any(env.get(p["key_var"]) for p in PROVIDER_PRESETS.values())
    table.add_row("API key", "[ok]configured[/ok]" if key_ok else "[warn]none (demo echo mode)[/warn]")
    for port in PORTS:
        table.add_row(f"Port :{port}", "[warn]busy[/warn]" if port_in_use(port) else "[ok]free[/ok]")
    try:
        import crawl4ai  # type: ignore  # noqa: F401

        table.add_row("Crawl4AI", "[ok]installed[/ok]")
    except Exception:
        table.add_row("Crawl4AI", "[muted]optional · not installed[/muted]")
    table.add_row("Rich UI", "[ok]yes[/ok]" if HAS_RICH else "[warn]plain fallback[/warn]")
    return table


def doctor() -> int:
    banner()
    step("Doctor")
    console.print(diagnose())
    console.print(probe_health())
    issues = 0
    good, _ = check_python()
    if not good:
        issues += 1
        err("Python < 3.11")
    if not venv_python().is_file():
        issues += 1
        err("Missing .venv — run: nlm setup")
    elif REQ.exists():
        digest = file_sha256(REQ)
        prev = REQ_HASH.read_text(encoding="utf-8").strip() if REQ_HASH.exists() else ""
        if digest != prev:
            issues += 1
            warn("requirements.txt changed since last install — run: nlm repair")
    if not ENV_PATH.exists():
        issues += 1
        warn("Missing .env — run: nlm config")
    if not (ROOT / "web-static" / "index.html").is_file():
        warn("Missing web-static — UI empty until build")
    if issues == 0:
        ok("Doctor: no critical issues")
    else:
        warn(f"Doctor: {issues} issue(s) — try: nlm repair")
    return 0 if issues == 0 else 1


def repair() -> None:
    step("Auto repair")
    ensure_dirs()
    if not ensure_venv():
        return
    if not install_deps(force=True):
        err("Dependency repair failed")
        return
    ensure_env_file()
    fix_docker_urls_in_env()
    free_ports()
    check_web_static(offer_build=False)
    ok("Repair pass complete")
    console.print(diagnose())


def setup_flow(
    *,
    force: bool = False,
    with_crawl: bool = False,
    skip_config: bool = False,
    quiet_ok: bool = False,
) -> bool:
    """Install/repair local env. Prompts only on first-time / when needed / TTY."""
    if quiet_ok and not needs_setup(force=force) and not with_crawl:
        ensure_dirs()
        ensure_env_file()
        fix_docker_urls_in_env()
        ok("Environment already ready — skipping interactive setup")
        return True

    banner()
    step("Environment check")
    console.print(diagnose())
    good, _ = check_python()
    if not good:
        err("Upgrade Python to 3.11+ first")
        return False
    if not ensure_venv():
        return False
    if Path(sys.executable).resolve() != venv_python().resolve() and venv_python().is_file():
        reexec_in_venv()
        return False  # unreachable on POSIX; Windows raises SystemExit

    ensure_dirs()
    if not install_deps(force=force, with_crawl=with_crawl):
        err("Dependency install failed — try another network / nlm repair")
        return False
    ensure_env_file()
    fix_docker_urls_in_env()

    first_time = not _has_any_api_key()
    if not skip_config:
        if first_time:
            if auto_yes() or not sys.stdin.isatty():
                info("No API key — demo echo mode (later: nlm config)")
            elif confirm("未检测到模型 API Key，运行配置向导？", default=True):
                config_wizard()
            else:
                info("Demo echo mode — later: nlm config")
        elif not auto_yes() and sys.stdin.isatty() and confirm("运行模型配置向导？", default=False):
            config_wizard()

    if with_crawl:
        install_crawl(ask=False)
    elif first_time and not auto_yes() and sys.stdin.isatty() and confirm(
        "安装网页爬取能力 (Crawl4AI)？", default=False
    ):
        install_crawl(ask=False)

    check_web_static(offer_build=first_time and sys.stdin.isatty() and not auto_yes())
    ok("Setup finished")
    return True


def auto_yes() -> bool:
    """Non-interactive mode: NLM_YES=1 or --yes (set via env by main)."""
    return os.environ.get("NLM_YES", "").strip().lower() in ("1", "true", "yes", "y")


def confirm(prompt: str, *, default: bool = True) -> bool:
    if auto_yes():
        return default
    if not sys.stdin.isatty():
        return default
    try:
        if HAS_RICH:
            return bool(Confirm.ask(prompt, default=default))
    except Exception as exc:
        # Python 3.13 + old rich: ModuleNotFoundError unicode17-0-0 during render
        print(f"[nlm] prompt fallback ({exc.__class__.__name__})", flush=True)
    return bool(_PlainConfirm.ask(prompt, default=default))


def ask_text(prompt: str, *, default: str = "", password: bool = False, choices: Optional[List[str]] = None) -> str:
    try:
        if HAS_RICH:
            kwargs: Dict[str, Any] = {"default": default}
            if password:
                kwargs["password"] = True
            if choices is not None:
                kwargs["choices"] = choices
            return str(Prompt.ask(prompt, **kwargs))
    except Exception as exc:
        print(f"[nlm] prompt fallback ({exc.__class__.__name__})", flush=True)
    return str(_PlainPrompt.ask(prompt, default=default, password=password, choices=choices))


def deps_hash_ok() -> bool:
    if not REQ.exists():
        return True
    digest = file_sha256(REQ)
    prev = REQ_HASH.read_text(encoding="utf-8").strip() if REQ_HASH.exists() else ""
    return digest == prev


def venv_imports_ok() -> bool:
    if not venv_python().is_file():
        return False
    try:
        subprocess.check_output(
            [str(venv_python()), "-c", "import fastapi, uvicorn, pydantic"],
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return True
    except Exception:
        return False


def needs_setup(*, force: bool = False) -> bool:
    if force:
        return True
    if not venv_python().is_file():
        return True
    if not ENV_PATH.exists():
        return True
    if not deps_hash_ok():
        return True
    if not venv_imports_ok():
        return True
    return False


def reexec_in_venv() -> None:
    """Re-run this script under .venv (Windows-safe: subprocess, not execv)."""
    # Never replace the process while pytest owns it (would look like exit code 2).
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("refusing to re-exec under pytest; run via `nlm` CLI instead")
    target = [str(venv_python()), str(Path(__file__).resolve()), *sys.argv[1:]]
    info(f"Switching into .venv …")
    if os.name == "nt":
        raise SystemExit(subprocess.call(target, cwd=str(ROOT)))
    os.execv(target[0], target)


def _has_any_api_key() -> bool:
    env = read_env()
    return any(bool(env.get(p["key_var"])) for p in PROVIDER_PRESETS.values())


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    free_ports()


def start_flow(*, open_browser: bool = True, skip_setup: bool = False) -> int:
    # Free ports first so a previous crashed run does not block install/start.
    free_ports()
    if not skip_setup:
        # One-command path: only full setup when something is missing;
        # never re-prompt crawl/config on every subsequent start.
        if not setup_flow(quiet_ok=True):
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
    urls = (
        "Web UI        http://127.0.0.1:8000\n"
        "Kernel        http://127.0.0.1:8001/health\n"
        "Orchestrator  http://127.0.0.1:8002/health\n"
        "Broker        memory://local\n\n"
        "Ctrl+C to stop · nlm stop · nlm status"
    )
    if HAS_RICH and Group is not None and Text is not None:
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
    else:
        print(urls, flush=True)

    env = local_runtime_env()
    py = str(venv_python() if venv_python().is_file() else sys.executable)

    if open_browser:
        def _open() -> None:
            if wait_healthy(60):
                try:
                    webbrowser.open("http://127.0.0.1:8000")
                except Exception:
                    pass

        threading.Thread(target=_open, daemon=True).start()

    popen_kwargs: Dict[str, Any] = {"cwd": str(ROOT), "env": env}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen([py, "-m", "src.entry_local"], **popen_kwargs)

    def _on_signal(signum: int, frame: Any) -> None:
        warn("Stopping services…")
        _terminate_process(proc)
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except Exception:
            pass

    try:
        return int(proc.wait() or 0)
    except KeyboardInterrupt:
        warn("Stopping…")
        _terminate_process(proc)
        return 0


def cmd_logs(*, follow: bool = True, lines: int = 80) -> int:
    ensure_dirs()
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        warn(f"No log files in {LOG_DIR}")
        info("Services may log to stdout only when started via nlm start")
        return 0
    target = logs[0]
    info(f"Tailing {target.name} (last {lines} lines)")
    try:
        content = target.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in content[-lines:]:
            print(line)
    except Exception as exc:
        err(str(exc))
        return 1
    if not follow:
        return 0
    info("Follow mode — Ctrl+C to stop")
    try:
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            while True:
                line = fh.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.4)
    except KeyboardInterrupt:
        return 0


def cmd_update() -> int:
    step("Update from git")
    if not (ROOT / ".git").is_dir():
        err("Not a git checkout — cannot pull")
        return 1
    try:
        run_cmd(["git", "pull", "--ff-only"])
        ok("git pull OK")
    except subprocess.CalledProcessError:
        err("git pull failed — resolve conflicts / check network")
        return 1
    return 0 if setup_flow(force=True, skip_config=True) else 1


def menu() -> int:
    banner()
    console.print(diagnose())
    console.print()
    rows = [
        ("1", "一键启动  — 环境检查 → 依赖 → 配置 → 启动（推荐）"),
        ("2", "安装 / 修复环境 (repair)"),
        ("3", "配置向导  — 供应商 / 模型 / API Key / Base URL"),
        ("4", "安装网页爬取 (Crawl4AI + Playwright)"),
        ("5", "状态检查 / Doctor"),
        ("6", "停止服务（释放 8000–8002）"),
        ("7", "打开 Web UI"),
        ("8", "查看日志 (logs)"),
        ("9", "更新代码 (git pull + setup)"),
        ("0", "退出"),
    ]
    if HAS_RICH:
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Key", style="accent", width=4)
        table.add_column("Action")
        for k, v in rows:
            table.add_row(k, v)
        console.print(Panel(table, title="Menu", border_style="cyan", box=box.ROUNDED))
    else:
        for k, v in rows:
            print(f"  {k}. {v}")

    choice = ask_text("选择", choices=[r[0] for r in rows], default="1")
    if choice == "0":
        return 0
    if choice == "1":
        return start_flow(open_browser=confirm("启动后打开浏览器？", default=True))
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
        return doctor()
    if choice == "6":
        free_ports()
        ok("Ports cleared")
        return 0
    if choice == "7":
        webbrowser.open("http://127.0.0.1:8000")
        ok("Opened http://127.0.0.1:8000")
        return 0
    if choice == "8":
        return cmd_logs()
    if choice == "9":
        return cmd_update()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    os.chdir(ROOT)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    parser = argparse.ArgumentParser(
        prog="nlm",
        description="Nexus Lark Mind local console — setup, configure, run, repair",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="One-shot setup + launch")
    p_start.add_argument("--no-open", action="store_true")
    p_start.add_argument("--skip-setup", action="store_true")
    p_start.add_argument("--yes", "-y", action="store_true", help="Non-interactive (accept defaults)")

    p_setup = sub.add_parser("setup", help="Install env/deps and configure")
    p_setup.add_argument("--force", action="store_true")
    p_setup.add_argument("--crawl", action="store_true")
    p_setup.add_argument("--skip-config", action="store_true")
    p_setup.add_argument("--yes", "-y", action="store_true")

    sub.add_parser("config", help="Provider / model / API wizard")
    sub.add_parser("crawl", help="Install Crawl4AI + Playwright")
    sub.add_parser("status", help="Health check")
    sub.add_parser("stop", help="Free local ports")
    p_restart = sub.add_parser("restart", help="Stop then start")
    p_restart.add_argument("--yes", "-y", action="store_true")
    p_restart.add_argument("--no-open", action="store_true")
    p_repair = sub.add_parser("repair", help="Auto-fix common issues")
    p_repair.add_argument("--yes", "-y", action="store_true")
    sub.add_parser("doctor", help="Full diagnostics")
    sub.add_parser("open", help="Open Web UI")
    p_update = sub.add_parser("update", help="git pull + re-run setup")
    p_update.add_argument("--yes", "-y", action="store_true")
    sub.add_parser("menu", help="Interactive menu (default)")

    p_logs = sub.add_parser("logs", help="Tail logs/")
    p_logs.add_argument("-n", "--lines", type=int, default=80)
    p_logs.add_argument("--no-follow", action="store_true")

    args = parser.parse_args(argv)
    if getattr(args, "yes", False):
        os.environ["NLM_YES"] = "1"
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
        return doctor()
    if cmd == "stop":
        free_ports()
        ok("Stopped")
        return 0
    if cmd == "restart":
        free_ports()
        return start_flow(open_browser=not getattr(args, "no_open", False), skip_setup=True)
    if cmd == "repair":
        repair()
        return 0
    if cmd == "doctor":
        return doctor()
    if cmd == "open":
        webbrowser.open("http://127.0.0.1:8000")
        return 0
    if cmd == "update":
        return cmd_update()
    if cmd == "logs":
        return cmd_logs(follow=not args.no_follow, lines=args.lines)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
