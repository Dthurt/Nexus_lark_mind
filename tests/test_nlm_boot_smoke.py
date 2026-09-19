"""Smoke tests for the nlm boot console (catches TextColumn / argparse regressions)."""

from __future__ import annotations

import importlib.util
import os
import py_compile
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "scripts" / "nlm_boot.py"

# Keep these out of the default suite (venv re-exec / full start). Dedicated CI step runs them.
pytestmark = pytest.mark.nlm_boot


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(args: list[str], *, timeout: int = 90, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = _env()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(BOOT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def _load_boot():
    spec = importlib.util.spec_from_file_location("nlm_boot", BOOT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_nlm_boot_compiles() -> None:
    py_compile.compile(str(BOOT), doraise=True)


def test_nlm_boot_help() -> None:
    proc = _run(["--help"], timeout=60)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    out = proc.stdout or ""
    assert "start" in out
    assert "repair" in out


def test_nlm_boot_status_smoke() -> None:
    """status/doctor must not crash even when services are down."""
    proc = _run(["status"], timeout=90)
    assert proc.returncode in (0, 1), proc.stderr or proc.stdout
    out = (proc.stdout or "") + (proc.stderr or "")
    assert "Python" in out or "Environment" in out or "Doctor" in out or "NEXUS" in out


def test_textcolumn_format_constant() -> None:
    src = BOOT.read_text(encoding="utf-8")
    bare = re.findall(r"TextColumn\(\s*\)", src)
    assert bare == [], f"bare TextColumn() found: {bare}"
    assert "TEXT_COL" in src


def test_quiet_setup_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quiet path must short-circuit when env is ready — never re-exec under pytest."""
    boot = _load_boot()
    os.environ["NLM_YES"] = "1"
    try:
        monkeypatch.setattr(boot, "needs_setup", lambda **_kwargs: False)
        monkeypatch.setattr(
            boot,
            "reexec_in_venv",
            lambda: (_ for _ in ()).throw(RuntimeError("reexec should not run")),
        )
        assert boot.setup_flow(quiet_ok=True) is True
    finally:
        os.environ.pop("NLM_YES", None)


def test_list_on_path_prefers_where_then_which(monkeypatch: pytest.MonkeyPatch) -> None:
    boot = _load_boot()
    monkeypatch.setattr(boot, "is_windows", lambda: True)

    def fake_check_output(*_args, **_kwargs):
        return "C:\\WindowsApps\\python.exe\nC:\\Python312\\python.exe\n"

    monkeypatch.setattr(boot.subprocess, "check_output", fake_check_output)
    hits = boot.list_on_path("python")
    assert hits[0].endswith("WindowsApps\\python.exe")
    assert hits[1].endswith("Python312\\python.exe")


def test_is_windows_store_stub() -> None:
    boot = _load_boot()
    assert boot.is_windows_store_stub(r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe")
    assert boot.is_windows_store_stub(r"C:/Users/x/AppData/Local/Microsoft/WindowsApps/python3.exe")
    assert not boot.is_windows_store_stub(r"C:\Users\x\AppData\Local\Programs\Python\Python312\python.exe")
    assert not boot.is_windows_store_stub(None)
    assert not boot.is_windows_store_stub("")


def test_probe_python_version_skips_store_stub() -> None:
    boot = _load_boot()
    assert boot.probe_python_version(r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe") is None


def test_is_supported_python_version() -> None:
    boot = _load_boot()
    assert boot.is_supported_python_version((3, 10, 12))
    assert boot.is_supported_python_version((3, 11, 0))
    assert boot.is_supported_python_version((3, 12, 8))
    assert boot.is_supported_python_version((3, 13, 1))
    assert not boot.is_supported_python_version((3, 9, 18))
    assert not boot.is_supported_python_version((3, 14, 0))
    assert not boot.is_supported_python_version(None)


def test_find_system_python_skips_stub_when_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    boot = _load_boot()
    stub = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe"
    monkeypatch.setattr(boot, "probe_python_version", lambda _exe: None)
    monkeypatch.setattr(boot.shutil, "which", lambda _name: stub)
    monkeypatch.setattr(boot, "list_on_path", lambda _name: [stub])
    monkeypatch.setattr(boot, "is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", r"Z:\nlm_no_such_local")
    monkeypatch.setenv("ProgramFiles", r"Z:\nlm_no_such_pf")
    monkeypatch.setenv("ProgramFiles(x86)", r"Z:\nlm_no_such_pfx86")
    assert boot.find_system_python() is None


def test_find_system_python_skips_stub_then_real(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    boot = _load_boot()
    stub = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe"
    real = str(tmp_path / "python.exe")
    Path(real).write_bytes(b"")

    def fake_probe(exe: str):
        if "WindowsApps" in exe:
            return None
        if os.path.normcase(os.path.abspath(exe)) == os.path.normcase(os.path.abspath(real)):
            return (3, 12, 8)
        return None

    monkeypatch.setattr(boot, "probe_python_version", fake_probe)
    monkeypatch.setattr(boot, "default_windows_python_exes", lambda: [])
    monkeypatch.setattr(boot, "list_on_path", lambda name: [stub, real] if name == "python" else [])
    monkeypatch.setattr(boot, "is_windows", lambda: True)
    monkeypatch.setattr(boot.sys, "executable", stub)
    assert boot.find_system_python() == real


def test_missing_python_help_text_noninteractive() -> None:
    boot = _load_boot()
    text = boot.missing_python_help_text(non_interactive=True)
    assert "3.10" in text
    assert "3.13" in text
    assert "非交互" in text
    if os.name == "nt":
        assert "winget" in text
    else:
        assert "apt-get" in text or "brew" in text


def test_resolve_or_install_python_noninteractive(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    boot = _load_boot()
    monkeypatch.setattr(boot, "find_system_python", lambda: None)
    monkeypatch.setattr(boot, "auto_yes", lambda: True)
    monkeypatch.setattr(boot, "try_install_system_python", lambda: (_ for _ in ()).throw(RuntimeError("must not install")))
    assert boot.resolve_or_install_python() is None
    out = capsys.readouterr().out
    assert "Python 3.10" in out
    assert "3.13" in out


def test_ensure_venv_messages_when_no_python(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    boot = _load_boot()
    monkeypatch.setattr(boot, "find_system_python", lambda: None)
    monkeypatch.setattr(boot, "auto_yes", lambda: True)
    monkeypatch.setattr(boot, "try_install_system_python", lambda: None)
    assert boot.ensure_venv() is False
    out = capsys.readouterr().out
    assert "Python" in out
    assert "3.10" in out


def test_confirm_respects_nlm_yes() -> None:
    boot = _load_boot()
    os.environ["NLM_YES"] = "1"
    try:
        assert boot.confirm("anything?", default=False) is False
        assert boot.confirm("anything?", default=True) is True
    finally:
        os.environ.pop("NLM_YES", None)


def test_pip_indexes_cn_first_official_last() -> None:
    boot = _load_boot()
    assert boot.PIP_INDEXES == (
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.aliyun.com/pypi/simple",
        "https://pypi.mirrors.ustc.edu.cn/simple",
        "https://pypi.org/simple",
    )
    cn = boot._pip_index_args(boot.PIP_INDEXES[0])
    assert cn[:2] == ["-i", boot.PIP_INDEXES[0]]
    assert "--trusted-host" in cn
    assert "pypi.tuna.tsinghua.edu.cn" in cn
    official = boot._pip_index_args(boot.PIP_INDEXES[-1])
    assert official == ["-i", "https://pypi.org/simple"]
    cmd = boot._build_pip_install_cmd(
        "python",
        ["-r", "requirements.txt"],
        boot.PIP_INDEXES[1],
        timeout="60",
    )
    assert cmd[:4] == ["python", "-m", "pip", "install"]
    assert "-i" in cmd and "https://mirrors.aliyun.com/pypi/simple" in cmd
    assert "--trusted-host" in cmd and "mirrors.aliyun.com" in cmd
    assert "-r" in cmd and "requirements.txt" in cmd


def test_rich_unicode_probe_or_plain_fallback() -> None:
    """Python 3.13 needs rich>=14.3 for unicode17; otherwise plain UI must work."""
    boot = _load_boot()
    # confirm must never raise even if rich is broken mid-call
    os.environ["NLM_YES"] = "1"
    try:
        assert boot.confirm("未检测到模型 API Key，运行配置向导？", default=True) is True
    finally:
        os.environ.pop("NLM_YES", None)
    if boot.HAS_RICH:
        from rich.cells import cell_len

        assert cell_len("测试") >= 2


@pytest.mark.skipif(
    os.environ.get("NLM_E2E", "").strip().lower() not in ("1", "true", "yes"),
    reason="set NLM_E2E=1 for full start→health→stop (slow; optional)",
)
def test_one_shot_start_becomes_healthy() -> None:
    """End-to-end: nlm start --yes --no-open → health OK → stop."""
    repair = _run(["repair", "--yes"], timeout=600)
    assert repair.returncode == 0, repair.stderr or repair.stdout

    env = _env()
    env["NLM_YES"] = "1"
    log_path = ROOT / "logs" / "nlm_pytest_e2e.log"
    log_path.parent.mkdir(exist_ok=True)
    # IMPORTANT: do not use PIPE (uvicorn logs fill the buffer and deadlock).
    with log_path.open("w", encoding="utf-8", errors="replace") as logf:
        proc = subprocess.Popen(
            [sys.executable, str(BOOT), "start", "--yes", "--no-open"],
            cwd=str(ROOT),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        healthy = False
        try:
            deadline = time.time() + 90
            while time.time() < deadline:
                if proc.poll() is not None:
                    text = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
                    raise AssertionError(f"nlm start exited early ({proc.returncode}): {text}")
                try:
                    import urllib.request

                    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1.5) as resp:
                        if 200 <= int(getattr(resp, "status", 200)) < 300:
                            healthy = True
                            break
                except Exception:
                    pass
                time.sleep(1)
            assert healthy, "services did not become healthy within 90s"
        finally:
            _run(["stop"], timeout=60)
            try:
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
