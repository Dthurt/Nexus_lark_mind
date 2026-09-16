"""Smoke tests for the nlm boot console (catches TextColumn / argparse regressions)."""

from __future__ import annotations

import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "scripts" / "nlm_boot.py"


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BOOT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=_env(),
    )


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
