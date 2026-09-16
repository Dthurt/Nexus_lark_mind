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

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "scripts" / "nlm_boot.py"


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


def test_quiet_setup_when_ready() -> None:
    boot = _load_boot()
    os.environ["NLM_YES"] = "1"
    try:
        if boot.needs_setup():
            # Ensure deps so quiet path can succeed on CI/dev machines
            assert boot.setup_flow(force=False, skip_config=True) is True
        assert boot.setup_flow(quiet_ok=True) is True
    finally:
        os.environ.pop("NLM_YES", None)


def test_confirm_respects_nlm_yes() -> None:
    boot = _load_boot()
    os.environ["NLM_YES"] = "1"
    try:
        assert boot.confirm("anything?", default=False) is False
        assert boot.confirm("anything?", default=True) is True
    finally:
        os.environ.pop("NLM_YES", None)


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
