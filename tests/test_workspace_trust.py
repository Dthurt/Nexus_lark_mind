"""Workspace trust gate — cwd Python extensions/hooks stay dark until trusted."""

from __future__ import annotations

import json
from pathlib import Path

from src.adapters.workspaces.store import WorkspaceStore
from src.core_kernel.extension_runtime import (
    discover_and_load_extensions,
    get_extension_registry,
)
from src.core_kernel.tool_hooks import run_pre_tool_hook
from src.core_kernel.workspace_trust import is_workspace_code_allowed


def test_untrusted_skips_cwd_extension(tmp_path: Path) -> None:
    ext = tmp_path / ".nlm" / "extensions"
    ext.mkdir(parents=True)
    (ext / "evil.py").write_text(
        "LOADED = True\n"
        "def register(api):\n"
        "    api.register_tool({'name': 'evil_tool', 'handler': lambda a: {'ok': True}})\n",
        encoding="utf-8",
    )
    store_path = tmp_path / "workspaces.json"
    store_path.write_text(
        json.dumps(
            {
                "workspaces": [
                    {
                        "id": "ws_x",
                        "path": str(tmp_path),
                        "title": "tmp",
                        "kind": "local",
                        "trusted": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert is_workspace_code_allowed(str(tmp_path), store_path=store_path) is False
    get_extension_registry().reset()
    reg = discover_and_load_extensions(str(tmp_path), reload=True, allow_workspace_code=False)
    assert "evil_tool" not in reg.tools
    assert any("evil.py" in (s.get("path") or "") for s in reg.skipped)
    assert reg.skip_reason == "workspace not trusted"


def test_trusted_loads_cwd_extension(tmp_path: Path) -> None:
    ext = tmp_path / ".nlm" / "extensions"
    ext.mkdir(parents=True)
    (ext / "demo.py").write_text(
        "def register(api):\n"
        "    api.register_tool({'name': 'demo_tool', 'handler': lambda a: {'ok': True}})\n",
        encoding="utf-8",
    )
    get_extension_registry().reset()
    reg = discover_and_load_extensions(str(tmp_path), reload=True, allow_workspace_code=True)
    assert "demo_tool" in reg.tools
    assert not reg.skipped


def test_bundled_plugins_volume_still_loads_when_untrusted(tmp_path: Path) -> None:
    get_extension_registry().reset()
    reg = discover_and_load_extensions(str(tmp_path), reload=True, allow_workspace_code=False)
    loaded = " ".join(reg.loaded).replace("\\", "/")
    assert "plugins_volume/extensions" in loaded or any(
        Path(p).name == "sample_logger.py" for p in reg.loaded
    )


def test_untrusted_skips_cwd_hooks(tmp_path: Path) -> None:
    hooks = tmp_path / ".nlm" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre_tool.py").write_text(
        "def pre_tool(ctx):\n    return {'block': True, 'reason': 'cwd hook'}\n",
        encoding="utf-8",
    )
    out = run_pre_tool_hook(
        tool="write_file",
        base="write_file",
        arguments={"path": "x"},
        cwd=str(tmp_path),
        allow_workspace_code=False,
    )
    assert out.get("block") is False


def test_workspace_store_trusted_roundtrip(tmp_path: Path) -> None:
    store = WorkspaceStore(path=tmp_path / "workspaces.json")
    rec = store.create(str(tmp_path), title="demo")
    assert rec.trusted is False
    assert rec.public()["trusted"] is False
    updated = store.set_trusted(rec.id, True)
    assert updated is not None and updated.trusted is True
    again = WorkspaceStore(path=tmp_path / "workspaces.json")
    loaded = again.get(rec.id)
    assert loaded is not None and loaded.trusted is True


def test_untrust_after_load_drops_cwd_tools(tmp_path: Path) -> None:
    """reload=False (agent loop) must not keep cwd tools after trust is revoked."""
    ext = tmp_path / ".nlm" / "extensions"
    ext.mkdir(parents=True)
    (ext / "sticky.py").write_text(
        "def register(api):\n"
        "    api.register_tool({'name': 'sticky_tool', 'handler': lambda a: {'ok': True}})\n",
        encoding="utf-8",
    )
    get_extension_registry().reset()
    trusted = discover_and_load_extensions(str(tmp_path), reload=False, allow_workspace_code=True)
    assert "sticky_tool" in trusted.tools
    dark = discover_and_load_extensions(str(tmp_path), reload=False, allow_workspace_code=False)
    assert "sticky_tool" not in dark.tools
    loaded = " ".join(dark.loaded).replace("\\", "/")
    assert "sticky.py" not in loaded


def test_path_case_mismatch_still_trusted(tmp_path: Path) -> None:
    from src.core_kernel.workspace_trust import paths_equivalent

    rec_path = str(tmp_path)
    flipped = rec_path.upper() if rec_path == rec_path.lower() else rec_path.lower()
    store_path = tmp_path / "workspaces.json"
    store_path.write_text(
        json.dumps(
            {
                "workspaces": [
                    {
                        "id": "ws_case",
                        "path": rec_path,
                        "title": "tmp",
                        "kind": "local",
                        "trusted": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    if not paths_equivalent(rec_path, flipped):
        # Case-sensitive filesystems must not treat C:\\Foo and c:\\foo as equal.
        assert rec_path != flipped
        return
    assert is_workspace_code_allowed(flipped, store_path=store_path) is True
