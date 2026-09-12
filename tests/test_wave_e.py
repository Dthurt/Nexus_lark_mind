"""Wave E unit tests: approval timeouts, Feishu cards, parallel setting."""

from src.adapters.feishu.cards import build_approval_card, build_ask_card
from src.common.approval_timeouts import approval_timeout_seconds
from src.common.config import Settings


def test_approval_timeouts_match_web():
    assert approval_timeout_seconds("run_shell") == 60
    assert approval_timeout_seconds("builtin_workspace_write_file") == 45
    assert approval_timeout_seconds("read_file") == 30


def test_feishu_approval_card_has_actions():
    card = build_approval_card(call_id="c1", name="run_shell", base="run_shell", arguments={"cmd": "ls"})
    actions = card["elements"][-1]["actions"]
    assert len(actions) == 3
    assert actions[0]["value"]["kind"] == "approval"
    assert actions[0]["value"]["call_id"] == "c1"


def test_feishu_ask_card_options():
    card = build_ask_card(
        call_id="c2",
        title="选择",
        questions=[
            {
                "id": "q1",
                "prompt": "用哪套？",
                "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            }
        ],
    )
    actions = card["elements"][-1]["actions"]
    kinds = {a["value"]["kind"] for a in actions}
    assert "ask_user" in kinds


def test_max_parallel_setting_default():
    s = Settings(agent_max_parallel_tool_calls=4)
    assert s.agent_max_parallel_tool_calls == 4
