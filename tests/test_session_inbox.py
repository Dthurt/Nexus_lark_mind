"""Unit tests for session inbox claim helpers."""

from src.common.session_inbox import (
    claim_kind,
    claim_next_queue,
    clear_inbox,
    list_inbox,
    new_inbox_item,
    push_inbox,
    remove_inbox,
)


def test_push_claim_steers_fifo():
    session: dict = {"inbox": []}
    a = new_inbox_item(kind="steer", content="first")
    b = new_inbox_item(kind="queue", content="queued")
    c = new_inbox_item(kind="steer", content="second")
    push_inbox(session, a)
    push_inbox(session, b)
    push_inbox(session, c)
    claimed = claim_kind(session, "steer")
    assert [x["content"] for x in claimed] == ["first", "second"]
    assert list_inbox(session) == [b]


def test_claim_next_queue_leaves_steers():
    session: dict = {"inbox": []}
    push_inbox(session, new_inbox_item(kind="steer", content="s"))
    push_inbox(session, new_inbox_item(kind="queue", content="q1"))
    push_inbox(session, new_inbox_item(kind="queue", content="q2"))
    got = claim_next_queue(session)
    assert got and got["content"] == "q1"
    left = list_inbox(session)
    assert [x["content"] for x in left] == ["s", "q2"]


def test_remove_and_clear():
    session: dict = {"inbox": []}
    item = new_inbox_item(kind="queue", content="x")
    push_inbox(session, item)
    removed = remove_inbox(session, item["id"])
    assert removed and removed["id"] == item["id"]
    push_inbox(session, new_inbox_item(kind="steer", content="y"))
    prev = clear_inbox(session)
    assert len(prev) == 1
    assert list_inbox(session) == []
