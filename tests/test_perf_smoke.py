"""Lightweight performance / hand-feel smoke gates (Wave E)."""

import time

from src.common.schemas import ChatMessage, ChatRole
from src.core_kernel.context_compact import compact_messages


def test_compaction_under_budget():
    """Heuristic compaction over a long transcript should stay snappy in CI."""
    msgs = [ChatMessage(role=ChatRole.SYSTEM, content="sys")]
    for i in range(120):
        msgs.append(ChatMessage(role=ChatRole.USER, content=f"user turn {i} " + ("x" * 2000)))
        msgs.append(
            ChatMessage(role=ChatRole.ASSISTANT, content=f"assistant turn {i} " + ("y" * 2000))
        )
    t0 = time.perf_counter()
    out = compact_messages(
        msgs,
        model_name="glm-4.7-flash",
        context_window=32_000,
        aggressiveness="aggressive",
    )
    elapsed = time.perf_counter() - t0
    assert len(out) < len(msgs)
    # Generous wall for shared CI runners; local is usually << 0.5s.
    assert elapsed < 2.5, f"compaction too slow: {elapsed:.3f}s"
