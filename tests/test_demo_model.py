"""Demo-mode model complete (no API key)."""

import pytest

from src.common.schemas import ChatMessage, ChatRole, ModelRequest
from src.core_kernel.model_gateway.gateway import ModelGateway


@pytest.mark.asyncio
async def test_openai_demo_complete():
    gw = ModelGateway()
    resp = await gw.complete(
        ModelRequest(
            provider="openai",
            messages=[ChatMessage(role=ChatRole.USER, content="ping")],
            stream=False,
        )
    )
    assert "ping" in resp.content
    assert resp.provider == "openai"
