"""Plugin manager tests."""

import json
from pathlib import Path

import pytest

from src.common.errors import PluginError
from src.common.schemas import PluginInvokeRequest
from src.core_kernel.plugin_runtime.lifecycle import PluginState
from src.core_kernel.plugin_runtime.manager import PluginManager, PREFS_PATH, _InProcessEchoManifest


@pytest.mark.asyncio
async def test_inprocess_echo_plugin():
    mgr = PluginManager()
    await mgr.load(_InProcessEchoManifest())
    result = await mgr.invoke(
        PluginInvokeRequest(plugin_id="builtin.echo", tool_name="echo", arguments={"hi": 1})
    )
    assert result.success is True
    assert result.result["echo"]["hi"] == 1


@pytest.mark.asyncio
async def test_enabled_vs_state_and_prefs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    mgr = PluginManager()
    await mgr.load(_InProcessEchoManifest())
    assert mgr.plugins["builtin.echo"].state == PluginState.READY
    listed = mgr.list_plugins()[0]
    assert listed["enabled"] is True
    assert listed["state"] == "ready"
    assert listed["health"]["status"] == "ok"

    await mgr.disable("builtin.echo")
    listed = mgr.list_plugins()[0]
    assert listed["enabled"] is False
    assert listed["state"] == "disabled"
    assert listed["health"]["last_teardown_at"]

    prefs = json.loads(Path("data/plugin_prefs.json").read_text(encoding="utf-8"))
    assert prefs["enabled"]["builtin.echo"] is False

    await mgr.enable("builtin.echo")
    assert mgr.plugins["builtin.echo"].state == PluginState.READY
    tools = mgr.list_tools()
    assert any(t["name"] == "echo" and t["openai_name"] for t in tools)


@pytest.mark.asyncio
async def test_reload_blocked_during_inflight(monkeypatch):
    mgr = PluginManager()
    await mgr.load(_InProcessEchoManifest())
    mgr._inflight_invokes = 1
    with pytest.raises(PluginError):
        await mgr.reload("builtin.echo")
    mgr._inflight_invokes = 0
    data = await mgr.reload("builtin.echo")
    assert any(p["plugin_id"] == "builtin.echo" for p in data)


@pytest.mark.asyncio
async def test_web_search_config_hints(monkeypatch):
    mgr = PluginManager()
    monkeypatch.setattr(mgr.settings, "tavily_api_key", "")
    monkeypatch.setattr(mgr.settings, "brave_api_key", "")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    from src.core_kernel.plugin_runtime.lifecycle import PluginManifest

    await mgr.load(
        PluginManifest(
            plugin_id="cli.web_search",
            name="web_search",
            kind="cli",
            tools=[{"name": "web_search", "description": "search"}],
            config={"script": "python", "tool_name": "web_search"},
        )
    )
    # disabled by default in load if we set enabled - force ready path
    await mgr.enable("cli.web_search")
    hints = mgr.list_plugins()[0]["config_hints"]
    assert any("TAVILY" in h for h in hints)
