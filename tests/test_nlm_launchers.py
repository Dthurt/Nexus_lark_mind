"""Static checks: launchers never silent-exit when Python is missing."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_nlm_cmd_skips_store_stub_and_prompts() -> None:
    text = _read("nlm.cmd")
    assert "WindowsApps" in text
    assert "python3" in text
    assert "maybe_pause" in text or "pause" in text
    assert "winget" in text
    assert "Python.Python.3.12" in text
    assert "--yes" in text
    assert "3.11" in text
    assert "3.13" in text
    assert "EnsurePythonOnly" in text or "自动安装" in text


def test_nlm_ps1_skips_store_stub_and_prompts() -> None:
    text = _read("nlm.ps1")
    assert "WindowsApps" in text
    assert "python3" in text
    assert "-All" in text
    assert "自动安装 Python 3.12" in text
    assert "打开说明" in text
    assert "winget" in text
    assert "Python.Python.3.12" in text
    assert "Update-NlmProcessPath" in text or "LOCALAPPDATA" in text
    assert "--yes" in text
    assert "ProgramFiles(x86)" in text


def test_nlm_unix_skips_stub_and_prompts() -> None:
    text = _read("nlm")
    assert "WindowsApps" in text
    assert "自动安装 Python 3.12" in text
    assert "apt-get" in text
    assert "brew" in text
    assert "--yes" in text
    assert "python3-venv" in text
    assert "xdg-open" in text


def test_scripts_nlm_cmd_skips_windowsapps() -> None:
    text = _read("scripts/nlm.cmd")
    assert "WindowsApps" in text
    assert "python3" in text
    assert "sys.version_info" in text
    assert "ProgramFiles" in text
    assert "nlm.cmd" in text


def test_start_local_ps1_not_silent_exit() -> None:
    text = _read("scripts/start_local.ps1")
    assert "WindowsApps" in text
    assert "python3" in text
    assert "-All" in text
    assert "sys.version_info" in text
    assert "EnsurePythonOnly" in text
    assert "nlm.ps1" in text
    assert "Wait-StartLocalIfClosing" in text
    assert "ProgramFiles" in text
    assert "Write-Error" not in text


def test_start_local_bat_pauses_on_double_click() -> None:
    text = _read("scripts/start_local.bat")
    assert "NLM_SHOULD_PAUSE" in text
    assert "pause" in text
    assert "/c" in text


def test_nlm_cmd_scans_programfiles_x86() -> None:
    text = _read("nlm.cmd")
    assert "ProgramFiles(x86)" in text
    assert "python3" in text
    assert "py -3" in text
