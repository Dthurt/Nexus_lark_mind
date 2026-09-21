"""web-static freshness helpers used by nlm start."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path


def _load_boot():
    boot = Path(__file__).resolve().parents[1] / "scripts" / "nlm_boot.py"
    spec = importlib.util.spec_from_file_location("nlm_boot_fresh", boot)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_web_static_stale_when_src_newer(tmp_path: Path):
    boot = _load_boot()
    web_src = tmp_path / "web" / "src"
    web_src.mkdir(parents=True)
    static = tmp_path / "web-static"
    static.mkdir()
    index = static / "index.html"
    src_file = web_src / "App.tsx"
    src_file.write_text("export default function App(){return null}", encoding="utf-8")
    index.write_text("<html></html>", encoding="utf-8")
    older = time.time() - 120
    newer = time.time()
    index.touch()
    # index older than src
    import os

    os.utime(index, (older, older))
    os.utime(src_file, (newer, newer))
    assert boot.web_static_is_stale(tmp_path) is True
    os.utime(index, (newer + 10, newer + 10))
    assert boot.web_static_is_stale(tmp_path) is False


def test_web_static_missing_counts_as_stale(tmp_path: Path):
    boot = _load_boot()
    (tmp_path / "web" / "src").mkdir(parents=True)
    assert boot.web_static_is_stale(tmp_path) is True
