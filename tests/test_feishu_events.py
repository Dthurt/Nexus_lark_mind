"""Feishu event parsing tests."""

from src.adapters.feishu.events import (
    classify_payload,
    parse_im_message,
    parse_url_verification,
    strip_mention_placeholders,
)


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
                "chat_type": "p2p",
                "message_type": "text",
                "content": '{"text":"你好"}',
            },
        },
    }
    kind, msg = classify_payload(payload)
    assert kind == "message"
    assert msg.text == "你好"
    assert msg.user_id == "ou_1"
    assert msg.chat_type == "p2p"
    assert msg.mentioned_bot is False


def test_group_message_requires_bot_mention():
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}, "sender_type": "user"},
            "message": {
                "message_id": "om_2",
                "chat_id": "oc_g",
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text":"@_user_1 帮我查一下"}',
                "mentions": [
                    {
                        "key": "@_user_1",
                        "id": {"open_id": "ou_bot", "id_type": "open_id"},
                        "name": "Nexus",
                        "mentioned_type": "bot",
                    }
                ],
            },
        },
    }
    msg = parse_im_message(payload)
    assert msg is not None
    assert msg.chat_type == "group"
    assert msg.mentioned_bot is True
    assert strip_mention_placeholders(msg.text) == "帮我查一下"


def test_group_message_without_mention():
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}, "sender_type": "user"},
            "message": {
                "message_id": "om_3",
                "chat_id": "oc_g",
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text":"普通群聊消息"}',
                "mentions": [],
            },
        },
    }
    msg = parse_im_message(payload)
    assert msg is not None
    assert msg.mentioned_bot is False
