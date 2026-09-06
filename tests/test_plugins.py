"""Plugin manager tests."""

import pytest

from src.common.schemas import PluginInvokeRequest
from src.core_kernel.plugin_runtime.manager import PluginManager, _InProcessEchoManifest


@pytest.mark.asyncio
async def test_inprocess_echo_plugin():
    mgr = PluginManager()
    await mgr.load(_InProcessEchoManifest())
    result = await mgr.invoke(
        PluginInvokeRequest(plugin_id="builtin.echo", tool_name="echo", arguments={"hi": 1})
    )
    assert result.success is True
    assert result.result["echo"]["hi"] == 1
