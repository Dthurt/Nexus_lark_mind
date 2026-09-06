"""Feishu event parsing tests."""

from src.adapters.feishu.events import classify_payload, parse_url_verification


def test_url_verification():
    payload = {"type": "url_verification", "challenge": "abc123", "token": "t"}
    assert parse_url_verification(payload) == "abc123"
    kind, data = classify_payload(payload)
    assert kind == "url_verification"
    assert data == "abc123"


def test_message_parse():
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": "text",
                "content": '{"text":"你好"}',
            },
        },
    }
    kind, msg = classify_payload(payload)
    assert kind == "message"
    assert msg.text == "你好"
    assert msg.user_id == "ou_1"
