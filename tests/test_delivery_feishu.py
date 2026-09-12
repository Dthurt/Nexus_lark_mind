"""Delivery workspace store + Feishu plan card."""

from pathlib import Path

from src.adapters.feishu.cards import build_plan_review_card
from src.common.delivery_store import DeliveryWriteError, write_delivery_to_workspace


def test_build_plan_review_card_actions():
    card = build_plan_review_card(
        call_id="pr_1",
        title="Plan review",
        plan="# Do thing\n\n```mermaid\ngraph TD\nA-->B\n```",
    )
    assert card["header"]["title"]["content"] == "计划审阅"
    actions = card["elements"][-1]["actions"]
    kinds = {a["value"]["action"] for a in actions}
    assert kinds == {"approve", "keep_planning", "deny"}
    assert all(a["value"]["kind"] == "plan_review" for a in actions)
    assert all(a["value"]["call_id"] == "pr_1" for a in actions)


def test_write_delivery_to_workspace(tmp_path: Path):
    out = write_delivery_to_workspace(
        str(tmp_path),
        file_name="Delivery-Demo.md",
        content="# hi\n",
    )
    assert out["ok"] is True
    assert out["path"] == ".nlm/deliveries/Delivery-Demo.md"
    assert (tmp_path / ".nlm" / "deliveries" / "Delivery-Demo.md").read_text(
        encoding="utf-8"
    ) == "# hi\n"


def test_write_delivery_rejects_ssh_kind(tmp_path: Path):
    try:
        write_delivery_to_workspace(
            str(tmp_path),
            file_name="x.md",
            content="x",
            workspace_kind="ssh",
        )
        assert False, "expected DeliveryWriteError"
    except DeliveryWriteError as exc:
        assert "local" in str(exc).lower()
