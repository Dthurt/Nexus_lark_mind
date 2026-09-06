"""Shared fixtures."""

import pytest

from src.common.schemas import ChannelType, ChatMessage, ChatRole, StandardTask


@pytest.fixture
def sample_task() -> StandardTask:
    return StandardTask(
        channel=ChannelType.WEB,
        user_id="tester",
        content="hello nexus",
        messages=[ChatMessage(role=ChatRole.USER, content="hello nexus")],
    )
